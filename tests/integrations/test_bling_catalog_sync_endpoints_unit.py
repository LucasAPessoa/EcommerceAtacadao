"""Mapeamento de erros do endpoint manual da importação (sem banco)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.v1.endpoints.integrations import bling
from src.services.catalog.catalog_sync_service import JobResult

ADMIN = SimpleNamespace(id=uuid4())


def _configured(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    monkeypatch.setattr(bling, "get_client_config", lambda: SimpleNamespace(bling_configured=value))


async def test_not_configured_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, False)
    service = SimpleNamespace(run_job=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await bling.start_catalog_sync(ADMIN, service)
    assert exc.value.status_code == 503
    service.run_job.assert_not_awaited()


async def test_inactive_connection_is_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, True)
    service = SimpleNamespace(
        run_job=AsyncMock(return_value=JobResult(uuid4(), "SKIPPED", None, False))
    )
    with pytest.raises(HTTPException) as exc:
        await bling.start_catalog_sync(ADMIN, service)
    assert exc.value.status_code == 409
    assert exc.value.detail == "Conexão com o Bling inativa"


async def test_busy_without_current_run_is_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch, True)
    service = SimpleNamespace(
        run_job=AsyncMock(return_value=JobResult(None, "BUSY", None, False)),
        list_runs=AsyncMock(return_value=SimpleNamespace(current=None)),
    )
    with pytest.raises(HTTPException) as exc:
        await bling.start_catalog_sync(ADMIN, service)
    assert exc.value.status_code == 409
