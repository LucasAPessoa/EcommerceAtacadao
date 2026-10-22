import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.services.sales import payment_maintenance_service as module
from src.services.sales.payment_maintenance_service import PaymentMaintenanceService


async def test_bling_check_failure_does_not_break_maintenance(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(_factory):
        raise RuntimeError("segredo-que-nao-deve-aparecer")

    monkeypatch.setattr(module, "run_connection_check", boom)
    service = PaymentMaintenanceService(session_factory=lambda: None, client=object())  # type: ignore[arg-type]

    await service._check_bling_connection()

    assert "bling_connection_check_crashed error=RuntimeError" in caplog.text
    assert "segredo" not in caplog.text


async def test_skips_silently_when_not_configured(client_config_override: Any) -> None:
    from src.services.integrations import bling_connection_service as svc

    client_config_override(bling=None)

    def factory():
        raise AssertionError("não deve abrir sessão")

    assert await svc.run_connection_check(factory) == "skipped_not_configured"


async def test_bling_check_timeout_is_logged_and_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def slow(_factory):
        await asyncio.sleep(5)

    monkeypatch.setattr(module, "run_connection_check", slow)
    service = PaymentMaintenanceService(session_factory=lambda: None, client=object())  # type: ignore[arg-type]

    await service._check_bling_connection(0.01)

    assert "bling_connection_check_timeout" in caplog.text


class _EmptyRepo:
    def __init__(self, _session) -> None:
        pass

    async def list_abandoned_order_ids(self, *_a):
        return []

    list_stale_reservation_order_ids = list_cancel_retry_order_ids = list_abandoned_order_ids


class _Session:
    async def rollback(self) -> None:
        pass


@asynccontextmanager
async def _factory():
    yield _Session()


async def test_run_skips_bling_check_when_out_of_budget_and_runs_it_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[float | None] = []

    async def spy(self, timeout_seconds=None):
        calls.append(timeout_seconds)

    monkeypatch.setattr(PaymentMaintenanceService, "_check_bling_connection", spy)
    service = PaymentMaintenanceService(_factory, client=object(), repository_factory=_EmptyRepo)  # type: ignore[arg-type]

    await service.run(time_budget_seconds=0.0)
    assert calls == []

    await service.run(time_budget_seconds=8.0)
    assert len(calls) == 1 and 0 < calls[0] <= 8.0
