import asyncio
import logging
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError

from src.celery_app import celery_app
from src.core.config import settings
from src.core.resilience import CircuitOpenError, backoff_delay
from src.db.session import SessionLocal, engine
from src.external.access_provision import access_provision
from src.external.errors import TRANSIENT_ERRORS
from src.external.hr_operations import hr_operations
from src.external.it_services import it_services
from src.onboarding.db import employee_manager
from src.provisioning.db import provisioning_task_manager
from src.provisioning.models import ProvisioningService, ProvisioningStatus

logger = logging.getLogger(__name__)

CALLS = {
    ProvisioningService.HR_OPERATIONS: hr_operations.register_employee,
    ProvisioningService.IT_SERVICES: it_services.provision_laptop,
    ProvisioningService.ACCESS_PROVISION: access_provision.grant_access,
}


@celery_app.task(bind=True)
def provision(self, task_id: int) -> None:
    try:
        delay = asyncio.run(_run(task_id))
    except SQLAlchemyError as exc:  # couldn't read/save state: try again, bounded
        delay = backoff_delay(
            self.request.retries + 1, settings.PROVISIONING_BACKOFF_BASE, settings.PROVISIONING_BACKOFF_CAP
        )
        raise self.retry(exc=exc, countdown=delay, max_retries=settings.PROVISIONING_MAX_ATTEMPTS)
    if delay is not None:
        # max_retries=None: the attempt budget is enforced in _execute, not by Celery.
        raise self.retry(countdown=delay, max_retries=None)


def dispatch_provisioning(task_ids: Sequence[int]) -> None:
    """Enqueue tasks. Never raises: rows are already saved, so a broker outage only delays them."""
    for task_id in task_ids:
        try:
            provision.delay(task_id)
        except Exception:
            logger.exception("Could not enqueue provisioning task %s", task_id)


async def _run(task_id: int) -> float | None:
    try:
        return await _execute(task_id)
    finally:
        await engine.dispose()  # pooled connections are bound to this run's event loop


async def _execute(task_id: int) -> float | None:
    """Run one task. Returns seconds to wait before retrying, or None when it is finished."""
    tasks = provisioning_task_manager
    async with SessionLocal() as db:
        task = await tasks.get(db, task_id)
        if task is None or task.status is not ProvisioningStatus.PENDING:
            return None
        employee = await employee_manager.get(db, task.employee_id)
        await db.commit()  # no transaction held during the network call

        if employee is None:
            await tasks.record(db, task, ProvisioningStatus.FAILED, error="employee not found")
            return None

        service = task.service
        attempts = task.attempts + 1
        try:
            ok = await CALLS[service](employee.email, idempotency_key=f"employee-{employee.id}:{service.value}")
        except CircuitOpenError as exc:
            # Never reached the service: don't charge an attempt, try again after cooldown.
            return max(1.0, exc.retry_after)
        except TRANSIENT_ERRORS as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempts >= settings.PROVISIONING_MAX_ATTEMPTS:
                logger.error("Task %s (%s) failed after %s attempts: %s", task_id, service.value, attempts, error)
                await tasks.record(db, task, ProvisioningStatus.FAILED, attempts=attempts, error=error)
                return None
            delay = backoff_delay(attempts, settings.PROVISIONING_BACKOFF_BASE, settings.PROVISIONING_BACKOFF_CAP)
            logger.warning("Task %s (%s) attempt %s failed, retry in %.1fs: %s", task_id, service.value, attempts, delay, error)
            await tasks.record(db, task, ProvisioningStatus.PENDING, attempts=attempts, error=error)
            return delay
        except Exception as exc:
            logger.exception("Task %s (%s) failed permanently", task_id, service.value)
            await tasks.record(
                db, task, ProvisioningStatus.FAILED, attempts=attempts, error=f"{type(exc).__name__}: {exc}"
            )
            return None

        if ok:
            await tasks.record(db, task, ProvisioningStatus.SUCCEEDED, attempts=attempts)
        else:
            await tasks.record(
                db, task, ProvisioningStatus.FAILED, attempts=attempts, error="service rejected the request"
            )
        return None
