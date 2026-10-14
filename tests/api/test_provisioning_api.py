from src.provisioning import api
from src.provisioning.models import ProvisioningService, ProvisioningStatus
from tests.factories import make_employee, make_task


def test_status_lists_tasks(client, url, patch_async):
    tasks = [
        make_task(),
        make_task(service=ProvisioningService.IT_SERVICES, status=ProvisioningStatus.FAILED, attempts=5, last_error="boom"),
    ]
    patch_async(api.employee_manager, "get", return_value=make_employee())
    patch_async(api.provisioning_task_manager, "list_for_employee", return_value=tasks)

    res = client.get(url("/employees/1/provisioning"))

    assert res.status_code == 200
    assert res.json()[1] == {"service": "it_services", "status": "failed", "attempts": 5, "last_error": "boom"}


def test_status_employee_not_found(client, url, patch_async):
    patch_async(api.employee_manager, "get", return_value=None)

    assert client.get(url("/employees/99/provisioning")).status_code == 404
