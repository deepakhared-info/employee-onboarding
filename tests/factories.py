"""Factory helpers building domain objects, API payloads and CSV content for tests."""
from datetime import date
from types import SimpleNamespace

from src.onboarding.models import Proficiency
from src.onboarding.schemas import EmployeeImportResult, EmployeeListItem, EmployeeListResponse, SkillProficiency
from src.provisioning.models import ProvisioningService, ProvisioningStatus


def make_employee(**overrides):
    data = {"id": 1, "email": "john@example.com", "first_name": "John", "last_name": "Doe", "start_date": date(2026, 1, 1)}
    return SimpleNamespace(**{**data, **overrides})


def make_employee_skill(name="python", proficiency=Proficiency.ADVANCED, skill_id=1):
    return SimpleNamespace(skill=SimpleNamespace(id=skill_id, name=name), proficiency=proficiency)


def make_task(**overrides):
    data = {
        "id": 1,
        "employee_id": 1,
        "service": ProvisioningService.HR_OPERATIONS,
        "status": ProvisioningStatus.SUCCEEDED,
        "attempts": 1,
        "last_error": None,
    }
    return SimpleNamespace(**{**data, **overrides})


def make_list_response(n_items=1, **overrides):
    items = [
        EmployeeListItem(
            first_name="John",
            last_name="Doe",
            email=f"john{i}@example.com",
            start_date=date(2026, 1, 1),
            skills=[SkillProficiency(name="python", proficiency=Proficiency.ADVANCED)],
        )
        for i in range(n_items)
    ]
    return EmployeeListResponse(**{"items": items, "page": 1, "page_size": 20, "total": n_items, **overrides})


def make_import_result(**overrides):
    return EmployeeImportResult(**{"created": 1, "skipped": 0, "errors": [], "provisioning_queued": 1, **overrides})


def make_csv(rows=("John,Doe,john@example.com,2026-01-01",)) -> bytes:
    return ("first_name,last_name,email,start_date\n" + "\n".join(rows)).encode()


def csv_upload(content: bytes | None = None, filename="employees.csv"):
    """`files=` kwarg for the import endpoint."""
    return {"file": (filename, make_csv() if content is None else content, "text/csv")}


def skills_payload(*skills):
    """skills_payload(("python", "expert"), ...) -> request body for the assign-skills endpoint."""
    return {"skills": [{"name": n, "proficiency": p} for n, p in skills]}
