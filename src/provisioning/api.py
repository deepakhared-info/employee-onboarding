from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.onboarding.db import employee_manager
from src.provisioning.db import provisioning_task_manager
from src.provisioning.schemas import ProvisioningTaskRead

router = APIRouter()


@router.get('/employees/{employee_id}/provisioning', response_model=list[ProvisioningTaskRead])
async def provisioning_status(employee_id: int, db: AsyncSession = Depends(get_db)):
    if not await employee_manager.get(db, employee_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return await provisioning_task_manager.list_for_employee(db, employee_id=employee_id)
