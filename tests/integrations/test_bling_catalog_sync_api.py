"""Contrato HTTP da importação do catálogo (spec 006): API local + Bling simulado.

Exige as variáveis do ``scripts/run_api_tests.sh``. O catálogo semeado não é afetado: o Bling
simulado fica sem produtos e a guarda de varredura vazia impede desativações.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from src.core import crypto
from tests.conftest import API_V1_PREFIX, auth_headers

BASE = f"{API_V1_PREFIX}/integrations/bling/catalog-sync"
RUN_KEYS = {
    "id",
    "trigger",
    "status",
    "started_at",
    "finished_at",
    "counts",
    "errors",
    "reason",
}
COUNT_KEYS = {"created", "updated", "deactivated", "blocked", "unchanged", "failed"}


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_env("DATABASE_URL"), poolclass=NullPool)
    yield engine
    await engine.dispose()


async def _clean(db: AsyncEngine) -> None:
    async with db.begin() as conn:
        await conn.execute(text("UPDATE catalog_sync_state SET current_run_id = NULL"))
        for table in (
            "catalog_sync_runs",
            "bling_connection_events",
            "bling_authorization_attempts",
            "bling_connections",
        ):
            await conn.execute(text(f"DELETE FROM {table}"))


@pytest_asyncio.fixture
async def fake(db: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=_env("BLING_FAKE_URL"), timeout=10.0) as c:
        assert (await c.post("/__control/reset")).status_code == 200
        await _clean(db)
        yield c
    await _clean(db)


async def _connect(db: AsyncEngine, status: str = "CONNECTED") -> None:
    access, version = crypto.encrypt("access-test")
    refresh, _ = crypto.encrypt("refresh-test")
    async with db.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO bling_connections (id, singleton, status, company_id, "
                "access_token_enc, refresh_token_enc, key_version, access_expires_at, "
                "created_at, updated_at) VALUES (gen_random_uuid(), true, "
                "CAST(:status AS blingconnectionstatusenum), 'company-a', :a, :r, :v, :exp, "
                "now(), now())"
            ),
            {
                "status": status,
                "a": access,
                "r": refresh,
                "v": version,
                "exp": datetime.utcnow() + timedelta(hours=1),
            },
        )


def _assert_run(run: dict[str, Any]) -> None:
    assert RUN_KEYS <= set(run)
    assert set(run["counts"]) == COUNT_KEYS
    assert len(run["errors"]) <= 50
    assert "access-" not in str(run) and "refresh-" not in str(run)


class TestAuth:
    async def test_requires_authentication(self, client: httpx.AsyncClient) -> None:
        assert (await client.post(BASE)).status_code == 401
        assert (await client.get(f"{BASE}/runs")).status_code == 401

    async def test_requires_admin(self, client: httpx.AsyncClient, user_token: str) -> None:
        assert (await client.post(BASE, headers=auth_headers(user_token))).status_code == 403
        resp = await client.get(f"{BASE}/runs", headers=auth_headers(user_token))
        assert resp.status_code == 403


class TestStart:
    async def test_inactive_connection_returns_409_and_records_skipped(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        fake: httpx.AsyncClient,
        db: AsyncEngine,
    ) -> None:
        resp = await client.post(BASE, headers=auth_headers(admin_token))
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Conexão com o Bling inativa"
        runs = (await client.get(f"{BASE}/runs", headers=auth_headers(admin_token))).json()["data"]
        assert runs["current"] is None
        assert [r["status"] for r in runs["items"]] == ["SKIPPED"]
        assert runs["items"][0]["reason"] == "bling_not_connected"
        assert "phase" not in runs["items"][0]

    async def test_runs_a_slice_and_returns_the_run(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        fake: httpx.AsyncClient,
        db: AsyncEngine,
    ) -> None:
        await _connect(db)
        resp = await client.post(BASE, headers=auth_headers(admin_token))
        assert resp.status_code == 200, resp.text
        run = resp.json()["data"]
        _assert_run(run)
        assert run["trigger"] == "MANUAL"
        # Bling simulado vazio: a varredura vazia nunca desativa o catálogo semeado.
        assert run["status"] in {"SUCCESS", "PARTIAL"}
        assert run["reason"] in {None, "scan_vazio"}
        assert run["counts"]["deactivated"] == 0
        assert "phase" not in run or run["phase"] is None

        listing = (await client.get(f"{BASE}/runs", headers=auth_headers(admin_token))).json()
        assert listing["data"]["current"] is None
        assert listing["data"]["items"][0]["id"] == run["id"]


class TestRuns:
    async def test_limit_is_validated_and_applied(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        headers = auth_headers(admin_token)
        for bad in (0, 101, -1):
            resp = await client.get(f"{BASE}/runs", params={"limit": bad}, headers=headers)
            assert resp.status_code == 422
        await client.post(BASE, headers=headers)  # SKIPPED
        await _connect(db)
        await client.post(BASE, headers=headers)
        await client.post(BASE, headers=headers)
        resp = await client.get(f"{BASE}/runs", params={"limit": 2}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data) == {"current", "items"} and len(data["items"]) == 2
        for item in data["items"]:
            _assert_run(item)
        started = [item["started_at"] for item in data["items"]]
        assert started == sorted(started, reverse=True)
