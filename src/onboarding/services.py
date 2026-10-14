from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.core.utils import CSVReader
from src.onboarding.db import (
    EmployeeDBManager,
    employee_manager,
    employee_skill_manager,
    skill_manager,
)
from src.onboarding.models import EmployeeSkill, Proficiency
from src.onboarding.schemas import (
    EmployeeCreate,
    EmployeeImportResult,
    EmployeeListItem,
    EmployeeListResponse,
    EmployeeSkillsSet,
    RowError,
    SkillProficiency,
)
from src.provisioning.db import provisioning_task_manager
from src.provisioning.processor import ProvisioningDispatcher
from src.provisioning.worker import provisioning_worker

PAGE_SIZE = 20
REQUIRED_COLUMNS = {"email", "first_name", "last_name", "start_date"}


class EmployeeService:
    def __init__(
        self,
        manager: EmployeeDBManager = employee_manager,
        dispatcher: ProvisioningDispatcher = provisioning_worker,
    ):
        self.manager = manager
        self.dispatcher = dispatcher

    async def import_from_csv(self, db: AsyncSession, content: bytes) -> EmployeeImportResult:
        """
        Parse a CSV and save new employees. Invalid rows and rows whose
        email already exists (in the DB or earlier in the file) are skipped.
        Employees and their provisioning tasks are saved in one transaction; the
        external calls themselves run later, outside the request.
        """
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

        created = 0
        if valid:
            try:
                employee_ids = await self.manager.insert_new(db, objs_in=valid)
                created = len(employee_ids)
                skipped += len(valid) - created
                task_ids = []
                if employee_ids:
                    tasks = await provisioning_task_manager.create_for_employees(
                        db, employee_ids=employee_ids
                    )
                    task_ids = [t.id for t in tasks]
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            if task_ids:
                self.dispatcher.dispatch(task_ids)

        return EmployeeImportResult(
            created=created, skipped=skipped, errors=errors, provisioning_queued=created
        )

    async def list_employees(
        self,
        db: AsyncSession,
        *,
        skill: str | None,
        min_proficiency: Proficiency | None,
        page: int,
    ) -> EmployeeListResponse:
        employees, total = await self.manager.search(
            db,
            skill=skill,
            min_proficiency=min_proficiency,
            offset=(page - 1) * PAGE_SIZE,
            limit=PAGE_SIZE,
        )
        items = [
            EmployeeListItem(
                id=e.id,
                first_name=e.first_name,
                last_name=e.last_name,
                email=e.email,
                start_date=e.start_date,
                skills=[
                    SkillProficiency(name=es.skill.name, proficiency=es.proficiency)
                    for es in e.skills
                ],
            )
            for e in employees
        ]
        return EmployeeListResponse(items=items, page=page, page_size=PAGE_SIZE, total=total)


employee_service = EmployeeService()


class SkillService:
    async def set_employee_skills(
        self, db: AsyncSession, employee_id: int, data: EmployeeSkillsSet
    ) -> list[EmployeeSkill]:
        try:
            if not await employee_manager.get_for_update(db, id=employee_id):
                raise NotFoundError("Employee not found")

            skills = await skill_manager.get_or_create_many(db, names=[a.name for a in data.skills])
            await employee_skill_manager.delete_for_employee(db, employee_id=employee_id)
            db.add_all(
                EmployeeSkill(
                    employee_id=employee_id, skill_id=skills[a.name].id, proficiency=a.proficiency
                )
                for a in data.skills
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return await employee_skill_manager.list_for_employee(db, employee_id=employee_id)


skill_service = SkillService()
