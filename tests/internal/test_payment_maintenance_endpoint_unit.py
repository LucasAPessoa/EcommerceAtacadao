from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.v1.endpoints.internal import jobs
from src.core.config import settings
from src.main import app
from src.services.sales.payment_maintenance_service import PaymentMaintenanceResult

URL = "/api/v1/internal/jobs/payment-maintenance"


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=PaymentMaintenanceResult(2, 1, 3, 0, False))
    monkeypatch.setattr(
        jobs, "get_payment_maintenance_service", lambda: type("S", (), {"run": mock})()
    )
    return mock


def test_endpoint_is_disabled_without_configured_token(
    monkeypatch: pytest.MonkeyPatch, run: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "MAINTENANCE_JOB_TOKEN", "")
    with TestClient(app) as client:
        response = client.post(URL, headers={"Authorization": "Bearer "})
    assert response.status_code == 404
    run.assert_not_awaited()


@pytest.mark.parametrize("header", [None, "Bearer errado", "Basic segredo", "segredo"])
def test_endpoint_rejects_missing_or_wrong_token(
    monkeypatch: pytest.MonkeyPatch, run: AsyncMock, header: str | None
) -> None:
    monkeypatch.setattr(settings, "MAINTENANCE_JOB_TOKEN", "segredo")
    with TestClient(app) as client:
        response = client.post(URL, headers={"Authorization": header} if header else {})
    assert response.status_code == 401
    run.assert_not_awaited()


def test_endpoint_runs_job_and_returns_counts(
    monkeypatch: pytest.MonkeyPatch, run: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "MAINTENANCE_JOB_TOKEN", "segredo")
    with TestClient(app) as client:
        response = client.post(URL, headers={"Authorization": "Bearer segredo"})
    assert response.status_code == 200
    assert response.json()["data"] == {
        "expired_reservations": 2,
        "expired_orders": 1,
        "cancel_retries": 3,
        "cancel_failures": 0,
        "interrupted_by_budget": False,
    }
    assert URL not in client.get("/openapi.json").json()["paths"]
    run.assert_awaited_once()
