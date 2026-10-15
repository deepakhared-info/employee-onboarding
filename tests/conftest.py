import os

# Must be set before src.* is imported: the engine is built from settings at import time (connects lazily).
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "postgresql+psycopg://test:test@localhost/test")

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.db.session import get_db  # noqa: E402
from src.routes import router  # noqa: E402


@pytest.fixture
def client():
    """App with the DB session stubbed out."""
    app = FastAPI()
    app.include_router(router, prefix=settings.API_PREFIX)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def url():
    """Build an API url: url("/employees") -> "/api/v1/employees"."""
    return lambda path: f"{settings.API_PREFIX}/v1{path}"


@pytest.fixture
def patch_async(monkeypatch):
    """patch_async(obj, "method", return_value=..., side_effect=...) -> the installed AsyncMock."""

    def _patch(obj, method, **kwargs):
        mock = AsyncMock(**kwargs)
        monkeypatch.setattr(obj, method, mock)
        return mock

    return _patch
