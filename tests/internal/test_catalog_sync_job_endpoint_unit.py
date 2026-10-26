from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.endpoints.internal import jobs
from src.core.config import settings
from src.main import app
from src.services.catalog.catalog_sync_service import JobResult

URL = "/api/v1/internal/jobs/catalog-sync"


class _Session:
    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def run_job(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(jobs, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(jobs, "build_catalog_client", lambda factory: object())
    monkeypatch.setattr(jobs, "CatalogSyncRepository", lambda session: object())
    monkeypatch.setattr(
        jobs, "CatalogSyncService", lambda repo, client: SimpleNamespace(run_job=mock)
    )
    monkeypatch.setattr(settings, "MAINTENANCE_JOB_TOKEN", "segredo")
    return mock


def test_disabled_without_configured_token(
    monkeypatch: pytest.MonkeyPatch, run_job: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "MAINTENANCE_JOB_TOKEN", "")
    with TestClient(app) as client:
        assert client.post(URL).status_code == 404
    run_job.assert_not_awaited()


@pytest.mark.parametrize("header", [None, "Bearer errado", "Basic segredo", "segredo"])
def test_rejects_missing_or_wrong_token(run_job: AsyncMock, header: str | None) -> None:
    with TestClient(app) as client:
        response = client.post(URL, headers={"Authorization": header} if header else {})
    assert response.status_code == 401
    run_job.assert_not_awaited()


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (JobResult(None, "BUSY", None, False), ("BUSY", None, None, False)),
        (JobResult(None, "IDLE", None, False), ("IDLE", None, None, False)),
        (JobResult(uuid4(), "RUNNING", "DETAILS", True), ("RUNNING", "DETAILS", True, True)),
    ],
)
def test_returns_job_contract(run_job: AsyncMock, result: JobResult, expected: tuple) -> None:
    run_job.return_value = result
    with TestClient(app) as client:
        response = client.post(URL, headers={"Authorization": "Bearer segredo"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"run_id", "status", "phase", "interrupted_by_budget"}
    assert data["status"] == expected[0] and data["phase"] == expected[1]
    assert data["interrupted_by_budget"] is expected[3]
    assert data["run_id"] == (str(result.run_id) if result.run_id else None)
