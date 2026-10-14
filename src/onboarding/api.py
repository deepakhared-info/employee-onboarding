from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import InvalidFileError
from src.db.session import get_db
from src.onboarding.schemas import EmployeeImportResult
from src.onboarding.services import employee_service

router = APIRouter()


@router.post('/employee/import', response_model=EmployeeImportResult)
async def import_employee(file: UploadFile, db: AsyncSession = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")
    try:
        return await employee_service.import_from_csv(db, await file.read())
    except InvalidFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
