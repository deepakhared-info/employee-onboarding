from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.manager import BaseDBManager
from src.onboarding.models import Employee


class EmployeeDBManager(BaseDBManager[Employee, BaseModel, BaseModel]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[Employee]:
        result = await db.execute(select(Employee).where(Employee.email == email))
        return result.scalars().first()


employee_manager = EmployeeDBManager(Employee)
