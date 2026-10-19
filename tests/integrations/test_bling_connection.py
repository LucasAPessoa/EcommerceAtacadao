"""Conexão Bling (US1): HTTP black-box contra a API local e o Bling simulado.

Exige as variáveis do ``scripts/run_api_tests.sh`` (BLING_FAKE_URL, TENANT_ID, FRONT_URL,
BLING_* e DATABASE_URL de um Postgres descartável). Falta de ambiente falha o teste.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, AsyncIterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from src.integrations.bling.state import create_state
from tests.conftest import API_V1_PREFIX, auth_headers

BASE = f"{API_V1_PREFIX}/integrations/bling"


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


def _result_url(result: str) -> str:
    return f"{_env('FRONT_URL')}/admin/integracoes/bling?resultado={result}"


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_env("DATABASE_URL"), poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def fake(db: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    """Bling simulado e tabelas Bling limpos antes de cada teste."""
    async with httpx.AsyncClient(base_url=_env("BLING_FAKE_URL"), timeout=10.0) as c:
        assert (await c.post("/__control/reset")).status_code == 200
        async with db.begin() as conn:
            for table in (
                "bling_connection_events",
                "bling_authorization_attempts",
                "bling_connections",
            ):
                await conn.execute(text(f"DELETE FROM {table}"))
        yield c


async def _configure(fake: httpx.AsyncClient, **values: Any) -> None:
    assert (await fake.post("/__control/config", json=values)).status_code == 200


async def _token_calls(fake: httpx.AsyncClient) -> list[dict[str, Any]]:
    calls = (await fake.get("/__control/calls")).json()
    return [c for c in calls if c["path"] == "/oauth/token"]


async def _start(client: httpx.AsyncClient, admin_token: str) -> str:
    resp = await client.post(f"{BASE}/connect", headers=auth_headers(admin_token))
    assert resp.status_code == 200, resp.text
    url = resp.json()["data"]["authorize_url"]
    assert url.startswith(f"{_env('BLING_AUTH_BASE_URL')}/oauth/authorize?")
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [_env("BLING_CLIENT_ID")]
    assert query["response_type"] == ["code"]
    return query["state"][0]


async def _callback(client: httpx.AsyncClient, **params: str) -> httpx.Response:
    resp = await client.get(f"{BASE}/callback", params=params)
    assert resp.status_code == 302, resp.text
    return resp


async def _counts(db: AsyncEngine) -> dict[str, Any]:
    async with db.connect() as conn:
        rows = (await conn.execute(text("SELECT count(*) FROM bling_connections"))).scalar_one()
        events = (
            (
                await conn.execute(
                    text("SELECT event FROM bling_connection_events ORDER BY created_at")
                )
            )
            .scalars()
            .all()
        )
        connected = (
            await conn.execute(
                text("SELECT count(*) FROM bling_connections WHERE status='CONNECTED'")
            )
        ).scalar_one()
    return {"rows": rows, "events": list(events), "connected": connected}


async def _connection(db: AsyncEngine) -> dict[str, Any]:
    async with db.connect() as conn:
        row = (await conn.execute(text("SELECT * FROM bling_connections"))).mappings().one()
    return dict(row)


class TestConnectHappyPath:
    @pytest.mark.asyncio
    async def test_connect_then_callback_connects_encrypted(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        state = await _start(client, admin_token)

        resp = await _callback(client, code="ok-code", state=state)

        assert resp.headers["location"] == _result_url("conectado")
        assert "access-" not in resp.text and "refresh-" not in resp.text
        conn = await _connection(db)
        assert conn["status"] == "CONNECTED"
        assert conn["company_id"] == "company-a"
        assert conn["company_name"] == "Empresa A Ltda"
        assert conn["connected_at"] is not None and conn["last_refreshed_at"] is not None
        assert conn["access_token_enc"] and b"access-" not in bytes(conn["access_token_enc"])
        assert conn["refresh_token_enc"] and b"refresh-" not in bytes(conn["refresh_token_enc"])
        assert conn["access_expires_at"] > datetime.utcnow() + timedelta(minutes=30)
        assert (await _counts(db))["events"] == ["CONNECTED"]
        calls = await _token_calls(fake)
        assert len(calls) == 1 and calls[0]["grant_type"] == "authorization_code"
        assert calls[0]["basic_ok"] is True

    @pytest.mark.asyncio
    async def test_connect_again_when_connected_returns_409(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient
    ):
        state = await _start(client, admin_token)
        await _callback(client, code="ok-code", state=state)

        resp = await client.post(f"{BASE}/connect", headers=auth_headers(admin_token))

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reloading_callback_does_not_duplicate(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        state = await _start(client, admin_token)
        await _callback(client, code="ok-code", state=state)

        again = await _callback(client, code="ok-code", state=state)

        assert again.headers["location"] == _result_url("invalido")
        counts = await _counts(db)
        assert counts["rows"] == 1 and counts["events"] == ["CONNECTED"]
        assert len(await _token_calls(fake)) == 1


class TestInvalidState:
    @pytest.mark.asyncio
    async def test_invalid_states_write_nothing(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        key, tenant = _env("BLING_STATE_SIGNING_KEY"), _env("TENANT_ID")
        real = await _start(client, admin_token)
        candidates = {
            "ausente": {"code": "ok-code"},
            "lixo": {"code": "ok-code", "state": "lixo"},
            "assinatura_errada": {"code": "ok-code", "state": create_state(tenant, "outra-chave")},
            "expirado": {"code": "ok-code", "state": create_state(tenant, key, ttl_seconds=-5)},
            "tenant_errado": {"code": "ok-code", "state": create_state("outra-loja", key)},
            "sem_tentativa": {"code": "ok-code", "state": create_state(tenant, key)},
            "adulterado": {
                "code": "ok-code",
                "state": real[:-2] + ("AA" if real[-2:] != "AA" else "BB"),
            },
        }

        for name, params in candidates.items():
            resp = await _callback(client, **params)
            assert resp.headers["location"] == _result_url("invalido"), name

        counts = await _counts(db)
        assert counts["rows"] == 0 and counts["events"] == []
        assert await _token_calls(fake) == []

    @pytest.mark.asyncio
    async def test_expired_attempt_is_rejected(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        state = await _start(client, admin_token)
        async with db.begin() as conn:
            await conn.execute(
                text("UPDATE bling_authorization_attempts SET expires_at = :t"),
                {"t": datetime.utcnow() - timedelta(minutes=1)},
            )

        resp = await _callback(client, code="ok-code", state=state)

        assert resp.headers["location"] == _result_url("invalido")
        counts = await _counts(db)
        assert counts["rows"] == 0 and counts["events"] == []
        assert await _token_calls(fake) == []


class TestRejections:
    @pytest.mark.asyncio
    async def test_user_denied_at_bling(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        state = await _start(client, admin_token)

        resp = await _callback(client, error="access_denied", state=state)

        assert resp.headers["location"] == _result_url("recusado")
        counts = await _counts(db)
        assert counts["connected"] == 0 and counts["events"] == ["CONNECT_REJECTED"]
        assert await _token_calls(fake) == []
        # Nova tentativa é possível (não ficou CONNECTED).
        await _start(client, admin_token)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["invalid_grant", "400", "429", "503"])
    async def test_token_exchange_failure_saves_nothing(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        fake: httpx.AsyncClient,
        db: AsyncEngine,
        mode: str,
    ):
        await _configure(fake, token_mode=mode)
        state = await _start(client, admin_token)

        resp = await _callback(client, code="ok-code", state=state)

        assert resp.headers["location"] == _result_url("recusado")
        counts = await _counts(db)
        assert counts["connected"] == 0 and counts["events"] == ["CONNECT_REJECTED"]

    @pytest.mark.asyncio
    async def test_different_company_is_rejected_and_same_company_reconnects(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _callback(client, code="ok-code", state=await _start(client, admin_token))
        # Simula "desconectado" mantendo a empresa vinculada (a rota de desconexão é US3).
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE bling_connections SET status='NOT_CONNECTED', "
                    "access_token_enc=NULL, refresh_token_enc=NULL"
                )
            )
        await _configure(fake, company={"id": "company-b", "nome": "Outra SA", "cnpj": "9"})

        resp = await _callback(client, code="ok-code", state=await _start(client, admin_token))

        assert resp.headers["location"] == _result_url("empresa_diferente")
        conn_row = await _connection(db)
        assert conn_row["status"] == "NOT_CONNECTED"
        assert conn_row["company_id"] == "company-a"
        assert conn_row["company_name"] == "Empresa A Ltda"
        assert conn_row["access_token_enc"] is None and conn_row["refresh_token_enc"] is None
        assert (await _counts(db))["events"] == ["CONNECTED", "CONNECT_REJECTED"]

        await _configure(fake, company={"id": "company-a", "nome": "Empresa A Ltda", "cnpj": "1"})
        resp = await _callback(client, code="ok-code", state=await _start(client, admin_token))

        assert resp.headers["location"] == _result_url("conectado")
        assert (await _connection(db))["status"] == "CONNECTED"


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, client: httpx.AsyncClient, user_token: str):
        resp = await client.post(f"{BASE}/connect", headers=auth_headers(user_token))

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: httpx.AsyncClient):
        resp = await client.post(f"{BASE}/connect")

        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_non_admin_does_not_create_attempt(
        self, client: httpx.AsyncClient, user_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await client.post(f"{BASE}/connect", headers=auth_headers(user_token))

        async with db.connect() as conn:
            n = (
                await conn.execute(text("SELECT count(*) FROM bling_authorization_attempts"))
            ).scalar_one()
        assert n == 0
