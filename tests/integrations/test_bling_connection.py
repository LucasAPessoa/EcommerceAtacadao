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
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core import crypto
from src.integrations.bling.errors import (
    BlingNotConnectedError,
    BlingReconnectRequiredError,
    BlingUnavailableError,
)
from src.integrations.bling.state import create_state
from src.services.integrations.bling_connection_service import (
    BlingTokenProvider,
    run_connection_check,
)
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
        calls = (await fake.get("/__control/calls")).json()
        assert len([c for c in calls if c["path"] == "/oauth/revoke"]) == 2

        await _configure(fake, company={"id": "company-a", "nome": "Empresa A Ltda", "cnpj": "1"})
        resp = await _callback(client, code="ok-code", state=await _start(client, admin_token))

        assert resp.headers["location"] == _result_url("conectado")
        assert (await _connection(db))["status"] == "CONNECTED"


class TestDifferentCompanyRevokeFailure:
    @pytest.mark.asyncio
    async def test_revoke_failure_does_not_change_result(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _callback(client, code="ok-code", state=await _start(client, admin_token))
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE bling_connections SET status='NOT_CONNECTED', "
                    "access_token_enc=NULL, refresh_token_enc=NULL"
                )
            )
        await _configure(
            fake, company={"id": "company-b", "nome": "B", "cnpj": "9"}, revoke_mode="503"
        )

        resp = await _callback(client, code="ok-code", state=await _start(client, admin_token))

        assert resp.headers["location"] == _result_url("empresa_diferente")
        assert (await _connection(db))["company_id"] == "company-a"


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


# ---------------------------------------------------------------- helpers US2-US4


async def _connect(client: httpx.AsyncClient, admin_token: str) -> None:
    state = await _start(client, admin_token)
    resp = await _callback(client, code="ok-code", state=state)
    assert resp.headers["location"] == _result_url("conectado")


async def _expire_access(db: AsyncEngine, minutes: int = -1) -> None:
    async with db.begin() as conn:
        await conn.execute(
            text("UPDATE bling_connections SET access_expires_at = :t"),
            {"t": datetime.utcnow() + timedelta(minutes=minutes)},
        )


def _provider(db: AsyncEngine) -> BlingTokenProvider:
    return BlingTokenProvider(async_sessionmaker(db, expire_on_commit=False))


def _refresh_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in calls if c.get("grant_type") == "refresh_token"]


class TestRefresh:
    @pytest.mark.asyncio
    async def test_concurrent_refresh_happens_once_and_rotation_is_persisted(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        import asyncio

        await _connect(client, admin_token)
        before = await _connection(db)
        old_refresh = crypto.decrypt(bytes(before["refresh_token_enc"]))
        await _expire_access(db, minutes=2)  # < 5 min restantes

        provider = _provider(db)
        tokens = await asyncio.gather(*(provider.get_token() for _ in range(4)))

        assert len(set(tokens)) == 1
        assert len(_refresh_calls(await _token_calls(fake))) == 1
        after = await _connection(db)
        assert crypto.decrypt(bytes(after["access_token_enc"])) == tokens[0]
        new_refresh = crypto.decrypt(bytes(after["refresh_token_enc"]))
        assert new_refresh != old_refresh and new_refresh.startswith("refresh-")
        assert after["status"] == "CONNECTED"
        assert after["access_expires_at"] > datetime.utcnow() + timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_valid_token_does_not_call_bling(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)

        await _provider(db).get_token()

        assert _refresh_calls(await _token_calls(fake)) == []

    @pytest.mark.asyncio
    async def test_refreshed_event_at_most_once_per_hour(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)
        provider = _provider(db)

        for _ in range(3):
            await _expire_access(db)
            await provider.get_token()

        assert (await _counts(db))["events"].count("REFRESHED") == 1
        assert len(_refresh_calls(await _token_calls(fake))) == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["invalid_grant", "400", "401"])
    async def test_permanent_refusal_requires_reconnect_then_same_company_reconnects(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        fake: httpx.AsyncClient,
        db: AsyncEngine,
        mode: str,
    ):
        await _connect(client, admin_token)
        await _expire_access(db)
        await _configure(fake, token_mode=mode)

        with pytest.raises(BlingReconnectRequiredError):
            await _provider(db).get_token()

        row = await _connection(db)
        assert row["status"] == "RECONNECT_REQUIRED"
        assert row["last_error_code"] and row["last_error_at"] is not None
        assert row["company_id"] == "company-a"
        assert (await _counts(db))["events"] == ["CONNECTED", "RECONNECT_REQUIRED"]
        with pytest.raises(BlingReconnectRequiredError):
            await _provider(db).get_token()

        await _configure(fake, token_mode="success")
        await _connect(client, admin_token)

        row = await _connection(db)
        assert row["status"] == "CONNECTED" and row["last_error_code"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["503", "429"])
    async def test_transient_failure_keeps_connected(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        fake: httpx.AsyncClient,
        db: AsyncEngine,
        mode: str,
    ):
        await _connect(client, admin_token)
        await _expire_access(db)
        await _configure(fake, token_mode=mode)

        with pytest.raises((BlingUnavailableError, Exception)) as exc:
            await _provider(db).get_token()
        assert not isinstance(exc.value, BlingReconnectRequiredError)

        row = await _connection(db)
        assert row["status"] == "CONNECTED" and row["last_error_code"]
        assert (await _counts(db))["events"] == ["CONNECTED", "REFRESH_FAILED"]
        # Recupera quando o Bling volta.
        await _configure(fake, token_mode="success")
        await _provider(db).get_token()
        assert (await _connection(db))["last_error_code"] is None

    @pytest.mark.asyncio
    async def test_not_connected_raises(self, fake: httpx.AsyncClient, db: AsyncEngine):
        with pytest.raises(BlingNotConnectedError):
            await _provider(db).get_token()


class TestPeriodicCheck:
    @pytest.mark.asyncio
    async def test_skips_without_connection_and_cleans_old_attempts(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _start(client, admin_token)
        async with db.begin() as conn:
            await conn.execute(
                text("UPDATE bling_authorization_attempts SET created_at = :t"),
                {"t": datetime.utcnow() - timedelta(days=2)},
            )

        result = await run_connection_check(async_sessionmaker(db, expire_on_commit=False))

        assert result == "skipped_not_connected"
        async with db.connect() as conn:
            n = (
                await conn.execute(text("SELECT count(*) FROM bling_authorization_attempts"))
            ).scalar_one()
        assert n == 0

    @pytest.mark.asyncio
    async def test_check_refreshes_and_calls_bling(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)
        await _expire_access(db, minutes=1)

        result = await run_connection_check(async_sessionmaker(db, expire_on_commit=False))

        assert result == "ok"
        calls = (await fake.get("/__control/calls")).json()
        assert len(_refresh_calls(calls)) == 1
        assert any(c["path"] == "/empresas/me/dados-basicos" for c in calls)

    @pytest.mark.asyncio
    async def test_revoked_at_bling_becomes_reconnect_required(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)
        await _configure(fake, company_mode="401")

        result = await run_connection_check(async_sessionmaker(db, expire_on_commit=False))

        assert result.startswith("failed_")
        assert (await _connection(db))["status"] == "RECONNECT_REQUIRED"
        assert (await _counts(db))["events"][-1] == "RECONNECT_REQUIRED"


class TestStatusAndDisconnect:
    @pytest.mark.asyncio
    async def test_status_in_three_states_without_tokens(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        headers = auth_headers(admin_token)

        resp = await client.get(f"{BASE}/status", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "NOT_CONNECTED" and data["company"] is None
        assert data["last_error"] is None and data["recent_events"] == []

        await _connect(client, admin_token)
        resp = await client.get(f"{BASE}/status", headers=headers)
        data = resp.json()["data"]
        assert data["status"] == "CONNECTED"
        assert data["company"] == {"id": "company-a", "name": "Empresa A Ltda"}
        assert data["connected_at"] and data["last_refreshed_at"]
        assert [e["event"] for e in data["recent_events"]] == ["CONNECTED"]
        for forbidden in ("access-", "refresh-", "token"):
            assert forbidden not in resp.text.lower().replace("recent_events", "")

        await _expire_access(db)
        await _configure(fake, token_mode="invalid_grant")
        with pytest.raises(BlingReconnectRequiredError):
            await _provider(db).get_token()
        resp = await client.get(f"{BASE}/status", headers=headers)
        data = resp.json()["data"]
        assert data["status"] == "RECONNECT_REQUIRED"
        assert data["last_error"]["code"] and data["last_error"]["at"]
        assert data["recent_events"][0]["event"] == "RECONNECT_REQUIRED"

    @pytest.mark.asyncio
    async def test_status_returns_only_10_latest_events(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        async with db.begin() as conn:
            for i in range(12):
                await conn.execute(
                    text(
                        "INSERT INTO bling_connection_events (id, event, reason, created_at) "
                        "VALUES (gen_random_uuid(), 'REFRESH_FAILED', :r, :t)"
                    ),
                    {"r": f"r{i}", "t": datetime.utcnow() - timedelta(minutes=12 - i)},
                )

        resp = await client.get(f"{BASE}/status", headers=auth_headers(admin_token))

        events = resp.json()["data"]["recent_events"]
        assert len(events) == 10 and events[0]["reason"] == "r11"

    @pytest.mark.asyncio
    async def test_disconnect_revokes_clears_tokens_keeps_company(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)

        resp = await client.post(f"{BASE}/disconnect", headers=auth_headers(admin_token))

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "NOT_CONNECTED"
        assert data["company"]["id"] == "company-a"
        assert "refresh-" not in resp.text and "access-" not in resp.text
        row = await _connection(db)
        assert row["status"] == "NOT_CONNECTED" and row["company_id"] == "company-a"
        assert row["access_token_enc"] is None and row["refresh_token_enc"] is None
        assert (await _counts(db))["events"] == ["CONNECTED", "DISCONNECTED"]
        calls = (await fake.get("/__control/calls")).json()
        assert [c for c in calls if c["path"] == "/oauth/revoke"][0]["basic_ok"] is True

        again = await client.post(f"{BASE}/disconnect", headers=auth_headers(admin_token))
        assert again.status_code == 409

    @pytest.mark.asyncio
    async def test_disconnect_succeeds_even_if_revoke_fails(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ):
        await _connect(client, admin_token)
        await _configure(fake, revoke_mode="503")

        resp = await client.post(f"{BASE}/disconnect", headers=auth_headers(admin_token))

        assert resp.status_code == 200
        assert (await _connection(db))["refresh_token_enc"] is None

    @pytest.mark.asyncio
    async def test_disconnect_when_never_connected_is_409(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient
    ):
        resp = await client.post(f"{BASE}/disconnect", headers=auth_headers(admin_token))

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_non_admin_cannot_read_status_or_disconnect(
        self, client: httpx.AsyncClient, user_token: str
    ):
        for method, path in (("GET", "status"), ("POST", "disconnect")):
            resp = await client.request(method, f"{BASE}/{path}", headers=auth_headers(user_token))
            assert resp.status_code == 403
            unauth = await client.request(method, f"{BASE}/{path}")
            assert unauth.status_code in (401, 403)
