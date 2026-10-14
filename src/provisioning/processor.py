import logging
from typing import Awaitable, Callable, Protocol, Sequence

from src.core.config import settings
from src.core.resilience import CircuitOpenError, backoff_delay
from src.db.session import SessionLocal
from src.external.access_provision import access_provision
from src.external.errors import TRANSIENT_ERRORS
from src.external.hr_operations import hr_operations
from src.external.it_services import it_services
from src.onboarding.db import EmployeeDBManager, employee_manager
from src.provisioning.db import ProvisioningTaskDBManager, provisioning_task_manager
from src.provisioning.models import ProvisioningService

logger = logging.getLogger(__name__)

ServiceCall = Callable[..., Awaitable[bool]]  # (email, *, idempotency_key) -> ok


class ProvisioningDispatcher(Protocol):
    """
    Told about freshly committed tasks so they run promptly. Must never raise: the tasks
    are already durable, so a failed dispatch only delays them until the next poll.
    Implementations: the in-process worker today, a Celery producer later.
    """

    def dispatch(self, task_ids: Sequence[int]) -> None: ...


class ProvisioningProcessor:
    def __init__(
        self,
        calls: dict[ProvisioningService, ServiceCall] | None = None,
        tasks: ProvisioningTaskDBManager = provisioning_task_manager,
        employees: EmployeeDBManager = employee_manager,
    ):
        self.calls = calls or {
            ProvisioningService.HR_OPERATIONS: hr_operations.register_employee,
            ProvisioningService.IT_SERVICES: it_services.provision_laptop,
            ProvisioningService.ACCESS_PROVISION: access_provision.grant_access,
        }
        self.tasks = tasks
        self.employees = employees

    def open_services(self) -> list[ProvisioningService]:
        """Services whose circuit breaker is currently rejecting calls."""
        return [
            service
            for service, call in self.calls.items()
            if (breaker := getattr(call, "breaker", None)) is not None and breaker.is_open
        ]

    async def process(self, task_id: int) -> None:
        """Claim and run one task. Safe to call concurrently or repeatedly for the same id."""
        # Tx 1: claim (committed immediately; no transaction is held during the network call).
        async with SessionLocal() as db:
            task = await self.tasks.claim(
                db, id=task_id, lease_seconds=settings.PROVISIONING_LEASE_SECONDS
            )
            if task is None:
                await db.rollback()
                return
            employee = await self.employees.get(db, task.employee_id)
            await db.commit()
            service, attempts = task.service, task.attempts
            email = employee.email if employee else None

        if email is None or attempts > settings.PROVISIONING_MAX_ATTEMPTS:
            reason = "employee not found" if email is None else "attempts exhausted (lease expired)"
            await self._record(task_id, attempts, self.tasks.mark_failed, error=reason)
            return

        try:
            ok = await self.calls[service](email, idempotency_key=f"employee-{task.employee_id}:{service.value}")
        except CircuitOpenError as exc:
            # Never reached the service: don't charge an attempt, try again after cooldown.
            await self._record(
                task_id, attempts, self.tasks.release, delay=max(1.0, exc.retry_after)
            )
        except TRANSIENT_ERRORS as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempts >= settings.PROVISIONING_MAX_ATTEMPTS:
                logger.error("Task %s (%s) failed after %s attempts: %s", task_id, service.value, attempts, error)
                await self._record(task_id, attempts, self.tasks.mark_failed, error=error)
            else:
                delay = backoff_delay(
                    attempts, settings.PROVISIONING_BACKOFF_BASE, settings.PROVISIONING_BACKOFF_CAP
                )
                logger.warning("Task %s (%s) attempt %s failed, retry in %.1fs: %s", task_id, service.value, attempts, delay, error)
                await self._record(
                    task_id, attempts, self.tasks.schedule_retry, delay=delay, error=error
                )
        except Exception as exc:
            logger.exception("Task %s (%s) failed permanently", task_id, service.value)
            await self._record(
                task_id, attempts, self.tasks.mark_failed, error=f"{type(exc).__name__}: {exc}"
            )
        else:
            if ok:
                await self._record(task_id, attempts, self.tasks.mark_succeeded)
            else:
                await self._record(
                    task_id, attempts, self.tasks.mark_failed, error="service rejected the request"
                )

    async def _record(self, task_id: int, attempts: int, outcome, **kwargs) -> None:
        """Tx 2: persist the outcome. If this fails the lease expires and the task is re-run
        (hence idempotency keys on the service calls)."""
        try:
            async with SessionLocal() as db:
                if not await outcome(db, id=task_id, attempts=attempts, **kwargs):
                    logger.warning("Task %s lost its claim before the result was saved", task_id)
                await db.commit()
        except Exception:
            logger.exception("Could not record outcome for task %s", task_id)


provisioning_processor = ProvisioningProcessor()
