from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.errors import InvalidFileError
from src.onboarding import services
from src.onboarding.models import Proficiency
from src.onboarding.services import PAGE_SIZE, EmployeeService
from tests.factories import make_csv, make_employee, make_employee_skill, make_task


@pytest.fixture
def db():
    return AsyncMock()


@pytest.fixture
def manager():
    m = MagicMock()
    m.get_by_email = AsyncMock(return_value=None)
    m.bulk_create = AsyncMock(side_effect=lambda db, objs_in, commit: [make_employee(id=i + 1) for i, _ in enumerate(objs_in)])
    m.search = AsyncMock(return_value=([], 0))
    return m


@pytest.fixture
def task_manager(monkeypatch):
    m = MagicMock()
    m.create_for_employees = AsyncMock(
        side_effect=lambda db, employee_ids: [make_task(id=100 + i) for i, _ in enumerate(employee_ids)]
    )
    monkeypatch.setattr(services, "provisioning_task_manager", m)
    return m


@pytest.fixture
def dispatcher():
    return MagicMock()


@pytest.fixture
def service(manager, dispatcher, task_manager):
    return EmployeeService(manager=manager, dispatcher=dispatcher)


class TestImportFromCsv:
    async def test_creates_employees_and_dispatches_tasks(self, service, db, manager, dispatcher):
        content = make_csv(["A,One,a@x.com,2026-01-01", "B,Two,B@X.com,2026-01-02"])

        result = await service.import_from_csv(db, content)

        assert (result.created, result.skipped, result.errors, result.provisioning_queued) == (2, 0, [], 2)
        assert [e.email for e in manager.bulk_create.await_args.kwargs["objs_in"]] == ["a@x.com", "b@x.com"]
        db.commit.assert_awaited_once()
        dispatcher.dispatch.assert_called_once_with([100, 101])

    async def test_invalid_rows_are_reported_not_saved(self, service, db, manager):
        content = make_csv(["A,One,not-an-email,2026-01-01", "B,Two,b@x.com,2026-01-02"])

        result = await service.import_from_csv(db, content)

        assert result.created == 1
        assert [(e.row, "email" in e.error) for e in result.errors] == [(2, True)]

    async def test_skips_duplicates_in_file_and_in_db(self, service, db, manager):
        manager.get_by_email.side_effect = lambda db, email: make_employee() if email == "db@x.com" else None
        content = make_csv(["A,One,a@x.com,2026-01-01", "A,Dup,A@x.com,2026-01-01", "D,Db,db@x.com,2026-01-01"])

        result = await service.import_from_csv(db, content)

        assert (result.created, result.skipped) == (1, 2)

    async def test_nothing_valid_skips_db_writes(self, service, db, manager, dispatcher):
        result = await service.import_from_csv(db, make_csv(["A,One,bad,2026-01-01"]))

        assert result.created == 0
        manager.bulk_create.assert_not_awaited()
        dispatcher.dispatch.assert_not_called()

    async def test_missing_columns(self, service, db):
        with pytest.raises(InvalidFileError, match="Missing columns"):
            await service.import_from_csv(db, b"email\na@x.com")

    async def test_db_failure_rolls_back_and_does_not_dispatch(self, service, db, manager, dispatcher):
        manager.bulk_create.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            await service.import_from_csv(db, make_csv())

        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()
        dispatcher.dispatch.assert_not_called()


class TestListEmployees:
    async def test_maps_employees_and_paginates(self, service, db, manager):
        employee = make_employee(skills=[make_employee_skill("python", Proficiency.EXPERT)])
        manager.search.return_value = ([employee], 41)

        res = await service.list_employees(db, skill="python", min_proficiency=Proficiency.ADVANCED, page=3)

        assert manager.search.await_args.kwargs == {
            "skill": "python",
            "min_proficiency": Proficiency.ADVANCED,
            "offset": 2 * PAGE_SIZE,
            "limit": PAGE_SIZE,
        }
        assert (res.page, res.page_size, res.total) == (3, PAGE_SIZE, 41)
        assert res.items[0].email == "john@example.com"
        assert [(s.name, s.proficiency) for s in res.items[0].skills] == [("python", Proficiency.EXPERT)]
