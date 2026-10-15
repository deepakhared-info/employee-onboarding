"""Provisioning Celery task against each external service and each failure mode."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.resilience import CircuitOpenError
from src.external.errors import PermanentServiceError, TransientServiceError
from src.provisioning import tasks
from src.provisioning.models import ProvisioningService, ProvisioningStatus
from tests.factories import make_employee, make_task

SERVICES = list(ProvisioningService)
Status = ProvisioningStatus


@pytest.fixture(autouse=True)
def fake_session(monkeypatch):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(tasks, "SessionLocal", MagicMock(return_value=ctx))
    monkeypatch.setattr(tasks, "engine", MagicMock(dispose=AsyncMock()))


@pytest.fixture
def task_manager(monkeypatch):
    m = MagicMock()
    m.get = AsyncMock()
    m.record = AsyncMock()
    monkeypatch.setattr(tasks, "provisioning_task_manager", m)
    return m


@pytest.fixture
def employees(monkeypatch):
    m = MagicMock()
    m.get = AsyncMock(return_value=make_employee())
    monkeypatch.setattr(tasks, "employee_manager", m)
    return m


@pytest.fixture
def run(task_manager, employees, monkeypatch):
    """run(service, call=None, attempts=0, status=PENDING) -> (delay returned by _execute, call)."""

    async def _run(service, call=None, attempts=0, status=Status.PENDING):
        call = call or AsyncMock(return_value=True)
        task_manager.get.return_value = make_task(service=service, attempts=attempts, status=status)
        monkeypatch.setattr(tasks, "CALLS", {s: call for s in ProvisioningService})
        return await tasks._execute(1), call

    return _run


def recorded(task_manager):
    """(status, kwargs) of the single record() call."""
    task_manager.record.assert_awaited_once()
    args, kwargs = task_manager.record.await_args
    return args[2], kwargs


@pytest.mark.parametrize("service", SERVICES)
class TestPerService:
    async def test_success(self, run, task_manager, service):
        delay, call = await run(service)

        assert delay is None
        call.assert_awaited_once_with("john@example.com", idempotency_key=f"employee-1:{service.value}")
        assert recorded(task_manager) == (Status.SUCCEEDED, {"attempts": 1})

    async def test_service_rejects_request(self, run, task_manager, service):
        delay, _ = await run(service, AsyncMock(return_value=False))

        assert delay is None
        status, kwargs = recorded(task_manager)
        assert (status, kwargs["error"]) == (Status.FAILED, "service rejected the request")

    @pytest.mark.parametrize("error", [TransientServiceError("503"), ConnectionError("reset"), TimeoutError()])
    async def test_transient_error_schedules_retry(self, run, task_manager, service, error):
        delay, _ = await run(service, AsyncMock(side_effect=error), attempts=1)

        assert delay > 0
        status, kwargs = recorded(task_manager)
        assert (status, kwargs["attempts"]) == (Status.PENDING, 2)
        assert type(error).__name__ in kwargs["error"]

    async def test_transient_error_on_last_attempt_fails_task(self, run, task_manager, service):
        delay, _ = await run(
            service,
            AsyncMock(side_effect=TransientServiceError("503")),
            attempts=settings.PROVISIONING_MAX_ATTEMPTS - 1,
        )

        assert delay is None
        status, kwargs = recorded(task_manager)
        assert status is Status.FAILED
        assert "TransientServiceError" in kwargs["error"]

    @pytest.mark.parametrize("error", [PermanentServiceError("bad request"), ValueError("boom")])
    async def test_permanent_error_fails_without_retry(self, run, task_manager, service, error):
        delay, _ = await run(service, AsyncMock(side_effect=error))

        assert delay is None
        status, kwargs = recorded(task_manager)
        assert status is Status.FAILED
        assert type(error).__name__ in kwargs["error"]

    async def test_open_circuit_retries_without_charging_attempt(self, run, task_manager, service):
        delay, _ = await run(service, AsyncMock(side_effect=CircuitOpenError(service.value, retry_after=12)))

        assert delay == 12
        task_manager.record.assert_not_awaited()


class TestGuards:
    @pytest.mark.parametrize("status", [Status.SUCCEEDED, Status.FAILED])
    async def test_finished_task_is_ignored(self, run, task_manager, status):
        delay, call = await run(ProvisioningService.HR_OPERATIONS, status=status)

        assert delay is None
        call.assert_not_awaited()
        task_manager.record.assert_not_awaited()

    async def test_unknown_task_is_ignored(self, run, task_manager):
        task_manager.get.return_value = None

        assert await tasks._execute(1) is None
        task_manager.record.assert_not_awaited()

    async def test_missing_employee_fails_task(self, run, task_manager, employees):
        employees.get.return_value = None

        delay, call = await run(ProvisioningService.HR_OPERATIONS)

        assert delay is None
        call.assert_not_awaited()
        assert recorded(task_manager)[1]["error"] == "employee not found"


class TestCeleryTask:
    def test_retries_with_delay_from_execute(self, monkeypatch):
        monkeypatch.setattr(tasks, "_run", AsyncMock(return_value=7.5))
        retry = MagicMock(side_effect=Retry())
        monkeypatch.setattr(tasks.provision, "retry", retry)

        with pytest.raises(Retry):
            tasks.provision.run(1)

        retry.assert_called_once_with(countdown=7.5, max_retries=None)

    def test_finished_task_does_not_retry(self, monkeypatch):
        monkeypatch.setattr(tasks, "_run", AsyncMock(return_value=None))

        assert tasks.provision.run(1) is None

    def test_db_error_retries_with_bounded_budget(self, monkeypatch):
        error = OperationalError("select", {}, Exception("db down"))
        monkeypatch.setattr(tasks, "_run", AsyncMock(side_effect=error))
        retry = MagicMock(side_effect=Retry())
        monkeypatch.setattr(tasks.provision, "retry", retry)

        with pytest.raises(Retry):
            tasks.provision.run(1)

        assert retry.call_args.kwargs["max_retries"] == settings.PROVISIONING_MAX_ATTEMPTS
