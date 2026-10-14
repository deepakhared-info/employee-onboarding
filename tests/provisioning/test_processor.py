"""ProvisioningProcessor against each external service (HR, IT, access) and each failure mode."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.core.resilience import CircuitOpenError
from src.external.access_provision import access_provision
from src.external.errors import PermanentServiceError, TransientServiceError
from src.external.hr_operations import hr_operations
from src.external.it_services import it_services
from src.provisioning import processor as processor_module
from src.provisioning.models import ProvisioningService
from src.provisioning.processor import ProvisioningProcessor
from tests.factories import make_employee, make_task

SERVICES = list(ProvisioningService)
REAL_SERVICES = {
    ProvisioningService.HR_OPERATIONS: hr_operations.register_employee,
    ProvisioningService.IT_SERVICES: it_services.provision_laptop,
    ProvisioningService.ACCESS_PROVISION: access_provision.grant_access,
}


@pytest.fixture(autouse=True)
def fake_session(monkeypatch):
    """Replace SessionLocal with a context manager yielding a mock session."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(processor_module, "SessionLocal", MagicMock(return_value=ctx))


@pytest.fixture
def task_manager():
    m = MagicMock()
    for name in ("claim", "mark_succeeded", "mark_failed", "schedule_retry", "release"):
        setattr(m, name, AsyncMock(return_value=True))
    return m


@pytest.fixture
def employees():
    m = MagicMock()
    m.get = AsyncMock(return_value=make_employee())
    return m


@pytest.fixture
def build(task_manager, employees):
    """build(service, call=None, attempts=1, calls=None) -> (processor, call); claim returns a task for `service`."""

    def _build(service, call=None, attempts=1, calls=None):
        call = call or AsyncMock(return_value=True)
        task_manager.claim.return_value = make_task(service=service, attempts=attempts)
        calls = calls or {s: call for s in ProvisioningService}
        return ProvisioningProcessor(calls=calls, tasks=task_manager, employees=employees), call

    return _build


@pytest.fixture
def reset_breakers():
    def reset():
        for call in REAL_SERVICES.values():
            call.breaker.on_success()

    reset()
    yield
    reset()


@pytest.mark.parametrize("service", SERVICES)
class TestPerService:
    async def test_success(self, build, task_manager, service):
        proc, call = build(service)

        await proc.process(1)

        call.assert_awaited_once_with("john@example.com", idempotency_key=f"employee-1:{service.value}")
        task_manager.mark_succeeded.assert_awaited_once()

    async def test_service_rejects_request(self, build, task_manager, service):
        proc, _ = build(service, AsyncMock(return_value=False))

        await proc.process(1)

        assert task_manager.mark_failed.await_args.kwargs["error"] == "service rejected the request"
        task_manager.mark_succeeded.assert_not_awaited()

    @pytest.mark.parametrize("error", [TransientServiceError("503"), ConnectionError("reset"), TimeoutError()])
    async def test_transient_error_schedules_retry(self, build, task_manager, service, error):
        proc, _ = build(service, AsyncMock(side_effect=error))

        await proc.process(1)

        kwargs = task_manager.schedule_retry.await_args.kwargs
        assert type(error).__name__ in kwargs["error"]
        assert kwargs["delay"] > 0
        task_manager.mark_failed.assert_not_awaited()

    async def test_transient_error_on_last_attempt_fails_task(self, build, task_manager, service):
        proc, _ = build(
            service,
            AsyncMock(side_effect=TransientServiceError("503")),
            attempts=settings.PROVISIONING_MAX_ATTEMPTS,
        )

        await proc.process(1)

        assert "TransientServiceError" in task_manager.mark_failed.await_args.kwargs["error"]
        task_manager.schedule_retry.assert_not_awaited()

    @pytest.mark.parametrize("error", [PermanentServiceError("bad request"), ValueError("boom")])
    async def test_permanent_error_fails_without_retry(self, build, task_manager, service, error):
        proc, _ = build(service, AsyncMock(side_effect=error))

        await proc.process(1)

        assert type(error).__name__ in task_manager.mark_failed.await_args.kwargs["error"]
        task_manager.schedule_retry.assert_not_awaited()

    async def test_open_circuit_releases_task(self, build, task_manager, service):
        proc, _ = build(service, AsyncMock(side_effect=CircuitOpenError(service.value, retry_after=12)))

        await proc.process(1)

        assert task_manager.release.await_args.kwargs["delay"] == 12
        task_manager.mark_failed.assert_not_awaited()
        task_manager.schedule_retry.assert_not_awaited()


class TestIsolationBetweenServices:
    @pytest.mark.parametrize("failing", SERVICES)
    async def test_failure_in_one_service_does_not_affect_others(self, build, task_manager, failing):
        calls = {s: AsyncMock(return_value=True) for s in ProvisioningService}
        calls[failing] = AsyncMock(side_effect=PermanentServiceError("down"))

        for service in SERVICES:
            proc, _ = build(service, calls=calls)
            await proc.process(1)

        assert task_manager.mark_failed.await_count == 1
        assert task_manager.mark_succeeded.await_count == len(SERVICES) - 1


class TestTaskGuards:
    async def test_unclaimable_task_is_ignored(self, build, task_manager):
        proc, call = build(ProvisioningService.HR_OPERATIONS)
        task_manager.claim.return_value = None

        await proc.process(1)

        call.assert_not_awaited()
        task_manager.mark_succeeded.assert_not_awaited()

    async def test_missing_employee_fails_task(self, build, task_manager, employees):
        proc, call = build(ProvisioningService.HR_OPERATIONS)
        employees.get.return_value = None

        await proc.process(1)

        call.assert_not_awaited()
        assert task_manager.mark_failed.await_args.kwargs["error"] == "employee not found"

    async def test_exhausted_attempts_fail_without_calling_service(self, build, task_manager):
        proc, call = build(ProvisioningService.IT_SERVICES, attempts=settings.PROVISIONING_MAX_ATTEMPTS + 1)

        await proc.process(1)

        call.assert_not_awaited()
        assert "exhausted" in task_manager.mark_failed.await_args.kwargs["error"]


@pytest.mark.usefixtures("reset_breakers")
@pytest.mark.parametrize("service", SERVICES)
class TestRealExternalServices:
    """Default wiring: real service objects with their circuit breakers; only the network wait is faked."""

    async def test_success(self, build, task_manager, monkeypatch, service):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        proc, _ = build(service, calls=REAL_SERVICES)

        await proc.process(1)

        task_manager.mark_succeeded.assert_awaited_once()

    async def test_outage_retries_then_opens_circuit(self, build, task_manager, monkeypatch, service):
        monkeypatch.setattr("asyncio.sleep", AsyncMock(side_effect=ConnectionError("unreachable")))
        proc, _ = build(service, calls=REAL_SERVICES)

        for _ in range(settings.CIRCUIT_FAILURE_THRESHOLD):
            await proc.process(1)
        assert task_manager.schedule_retry.await_count == settings.CIRCUIT_FAILURE_THRESHOLD
        assert proc.open_services() == [service]

        await proc.process(1)  # circuit open: service not called, attempt not charged
        task_manager.release.assert_awaited_once()
        assert task_manager.schedule_retry.await_count == settings.CIRCUIT_FAILURE_THRESHOLD
