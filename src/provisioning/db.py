from datetime import timedelta
from typing import Optional, Sequence

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.manager import BaseDBManager
from src.provisioning.models import ProvisioningService, ProvisioningStatus, ProvisioningTask


def _due():
    """Claimable: scheduled and pending, or running with an expired lease (worker died)."""
    return or_(
        and_(
            ProvisioningTask.status == ProvisioningStatus.PENDING,
            ProvisioningTask.next_run_at <= func.now(),
        ),
        and_(
            ProvisioningTask.status == ProvisioningStatus.RUNNING,
            ProvisioningTask.locked_until < func.now(),
        ),
    )


class ProvisioningTaskDBManager(BaseDBManager[ProvisioningTask, BaseModel, BaseModel]):
    async def create_for_employees(
        self, db: AsyncSession, *, employee_ids: Sequence[int]
    ) -> list[ProvisioningTask]:
        """Queue every service for each employee. Flushes only: the caller owns the commit."""
        tasks = [
            ProvisioningTask(employee_id=employee_id, service=service)
            for employee_id in employee_ids
            for service in ProvisioningService
        ]
        db.add_all(tasks)
        await db.flush()
        return tasks

    async def list_due_ids(
        self, db: AsyncSession, *, limit: int, exclude: Sequence[ProvisioningService] = ()
    ) -> list[int]:
        stmt = select(ProvisioningTask.id).where(_due())
        if exclude:
            stmt = stmt.where(ProvisioningTask.service.not_in(exclude))
        result = await db.execute(stmt.order_by(ProvisioningTask.next_run_at).limit(limit))
        return list(result.scalars().all())

    async def claim(
        self, db: AsyncSession, *, id: int, lease_seconds: int
    ) -> Optional[ProvisioningTask]:
        """
        Atomically take a due task (single UPDATE .. RETURNING, so only one runner wins).
        Counts the attempt up front so a task that keeps killing its runner still exhausts.
        """
        result = await db.execute(
            update(ProvisioningTask)
            .where(ProvisioningTask.id == id, _due())
            .values(
                status=ProvisioningStatus.RUNNING,
                locked_until=func.now() + timedelta(seconds=lease_seconds),
                attempts=ProvisioningTask.attempts + 1,
                updated_at=func.now(),
            )
            .returning(ProvisioningTask)
        )
        return result.scalars().first()

    async def _finish(self, db: AsyncSession, *, id: int, claimed: int, **values) -> bool:
        """Record an outcome only if we still hold the claim (same attempt, still running)."""
        result = await db.execute(
            update(ProvisioningTask)
            .where(
                ProvisioningTask.id == id,
                ProvisioningTask.status == ProvisioningStatus.RUNNING,
                ProvisioningTask.attempts == claimed,
            )
            .values(locked_until=None, updated_at=func.now(), **values)
        )
        return result.rowcount == 1

    async def mark_succeeded(self, db: AsyncSession, *, id: int, attempts: int) -> bool:
        return await self._finish(
            db, id=id, claimed=attempts, status=ProvisioningStatus.SUCCEEDED, last_error=None
        )

    async def mark_failed(self, db: AsyncSession, *, id: int, attempts: int, error: str) -> bool:
        return await self._finish(
            db, id=id, claimed=attempts, status=ProvisioningStatus.FAILED, last_error=error
        )

    async def schedule_retry(
        self, db: AsyncSession, *, id: int, attempts: int, delay: float, error: str
    ) -> bool:
        return await self._finish(
            db,
            id=id,
            claimed=attempts,
            status=ProvisioningStatus.PENDING,
            next_run_at=func.now() + timedelta(seconds=delay),
            last_error=error,
        )

    async def release(self, db: AsyncSession, *, id: int, attempts: int, delay: float) -> bool:
        """Put a task back without charging an attempt (e.g. circuit open: never called)."""
        return await self._finish(
            db,
            id=id,
            claimed=attempts,
            status=ProvisioningStatus.PENDING,
            next_run_at=func.now() + timedelta(seconds=delay),
            attempts=ProvisioningTask.attempts - 1,
        )

    async def list_for_employee(self, db: AsyncSession, *, employee_id: int) -> list[ProvisioningTask]:
        result = await db.execute(
            select(ProvisioningTask)
            .where(ProvisioningTask.employee_id == employee_id)
            .order_by(ProvisioningTask.id)
        )
        return list(result.scalars().all())


provisioning_task_manager = ProvisioningTaskDBManager(ProvisioningTask)
