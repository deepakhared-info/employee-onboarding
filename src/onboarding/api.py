from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import InvalidFileError, NotFoundError
from src.db.session import get_db
from src.onboarding.models import Proficiency
from src.onboarding.schemas import (
    EmployeeImportResult,
    EmployeeListResponse,
    EmployeeSkillRead,
    EmployeeSkillsSet,
)
from src.onboarding.services import employee_service, skill_service

router = APIRouter()


@router.post('/employees/import', response_model=EmployeeImportResult)
async def import_employee(file: UploadFile, db: AsyncSession = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")
    try:
        return await employee_service.import_from_csv(db, await file.read())
    except InvalidFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get('/employees', response_model=EmployeeListResponse)
async def list_employees(
    skill: Optional[str] = None,
    min_proficiency: Optional[Proficiency] = None,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    return await employee_service.list_employees(
        db, skill=skill, min_proficiency=min_proficiency, page=page
    )


@router.put('/employees/{employee_id}/skills', response_model=list[EmployeeSkillRead])
async def assign_skill(employee_id: int, data: EmployeeSkillsSet, db: AsyncSession = Depends(get_db)):
    try:
        return await skill_service.set_employee_skills(db, employee_id, data)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
