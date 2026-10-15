from typing import Sequence

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.manager import BaseDBManager
from src.provisioning.models import ProvisioningService, ProvisioningStatus, ProvisioningTask


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

    async def record(
        self,
        db: AsyncSession,
        task: ProvisioningTask,
        status: ProvisioningStatus,
        *,
        attempts: int | None = None,
        error: str | None = None,
    ) -> None:
        task.status = status
        task.last_error = error
        task.updated_at = func.now()
        if attempts is not None:
            task.attempts = attempts
        await db.commit()

    async def list_for_employee(self, db: AsyncSession, *, employee_id: int) -> list[ProvisioningTask]:
        result = await db.execute(
            select(ProvisioningTask)
            .where(ProvisioningTask.employee_id == employee_id)
            .order_by(ProvisioningTask.id)
        )
        return list(result.scalars().all())


provisioning_task_manager = ProvisioningTaskDBManager(ProvisioningTask)
