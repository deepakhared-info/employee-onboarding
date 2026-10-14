import pytest

from src.core.errors import InvalidFileError, NotFoundError
from src.onboarding.services import employee_service, skill_service
from tests.factories import (
    csv_upload,
    make_employee_skill,
    make_import_result,
    make_list_response,
    skills_payload,
)


class TestImportEmployees:
    def test_success(self, client, url, patch_async):
        mock = patch_async(employee_service, "import_from_csv", return_value=make_import_result(created=2))

        res = client.post(url("/employees/import"), files=csv_upload())

        assert res.status_code == 200
        assert res.json()["created"] == 2
        mock.assert_awaited_once()

    def test_rejects_non_csv(self, client, url):
        res = client.post(url("/employees/import"), files=csv_upload(filename="employees.txt"))

        assert res.status_code == 400

    def test_invalid_file_content(self, client, url, patch_async):
        patch_async(employee_service, "import_from_csv", side_effect=InvalidFileError("missing columns"))

        res = client.post(url("/employees/import"), files=csv_upload(b""))

        assert res.status_code == 400
        assert res.json()["detail"] == "missing columns"


class TestListEmployees:
    def test_success_with_filters(self, client, url, patch_async):
        mock = patch_async(employee_service, "list_employees", return_value=make_list_response(2))

        res = client.get(url("/employees"), params={"skill": "python", "min_proficiency": "advanced", "page": 2})

        assert res.status_code == 200
        assert res.json()["total"] == 2
        kwargs = mock.await_args.kwargs
        assert (kwargs["skill"], kwargs["min_proficiency"], kwargs["page"]) == ("python", "advanced", 2)

    @pytest.mark.parametrize("params", [{"page": 0}, {"min_proficiency": "godlike"}])
    def test_invalid_query(self, client, url, params):
        assert client.get(url("/employees"), params=params).status_code == 422


class TestAssignSkills:
    def test_success(self, client, url, patch_async):
        patch_async(skill_service, "set_employee_skills", return_value=[make_employee_skill("python", "expert")])

        res = client.put(url("/employees/1/skills"), json=skills_payload(("python", "expert")))

        assert res.status_code == 200
        assert res.json() == [{"skill": {"id": 1, "name": "python"}, "proficiency": "expert"}]

    def test_employee_not_found(self, client, url, patch_async):
        patch_async(skill_service, "set_employee_skills", side_effect=NotFoundError("Employee not found"))

        res = client.put(url("/employees/99/skills"), json=skills_payload(("python", "expert")))

        assert res.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            skills_payload(("python", "expert"), ("python", "beginner")),  # duplicate names
            skills_payload(("Python", "expert"), ("python", "beginner")),  # duplicate, different case
            skills_payload(("python", "godlike")),  # bad proficiency
            skills_payload(("  ", "expert")),  # blank name
        ],
    )
    def test_invalid_payload(self, client, url, payload):
        assert client.put(url("/employees/1/skills"), json=payload).status_code == 422
