from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import CSVReader
from src.onboarding.db import EmployeeDBManager, employee_manager
from src.onboarding.schemas import EmployeeCreate, EmployeeImportResult, RowError

REQUIRED_COLUMNS = {"email", "first_name", "last_name", "start_date"}


class EmployeeService:
    def __init__(self, manager: EmployeeDBManager = employee_manager):
        self.manager = manager

    async def import_from_csv(self, db: AsyncSession, content: bytes) -> EmployeeImportResult:
        """Parse a CSV and save new employees. Invalid rows and rows whose
        email already exists (in the DB or earlier in the file) are skipped."""
        reader = CSVReader(content, required_columns=REQUIRED_COLUMNS)

        valid: list[EmployeeCreate] = []
        errors: list[RowError] = []
        skipped = 0
        seen: set[str] = set()

        for row_no, row in enumerate(reader.read(), start=2):
            try:
                employee = EmployeeCreate(**{c: row.get(c, "") for c in REQUIRED_COLUMNS})
            except ValidationError as exc:
                msg = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
                errors.append(RowError(row=row_no, error=msg))
                continue

            if employee.email in seen or await self.manager.get_by_email(db, email=employee.email):
                skipped += 1
                continue
            seen.add(employee.email)
            valid.append(employee)

        if valid:
            await self.manager.bulk_create(db, objs_in=valid)

        return EmployeeImportResult(created=len(valid), skipped=skipped, errors=errors)


employee_service = EmployeeService()
