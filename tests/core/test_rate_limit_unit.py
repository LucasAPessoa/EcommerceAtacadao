import asyncio
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import exceptions as redis_exceptions

from src.core.config import Settings
from src.core.rate_limit import (
    ROUTE_POLICIES,
    RateLimitMiddleware,
    RedisRestRateLimiter,
    RedisTcpRateLimiter,
    client_ip,
    enforce_verified_webhook_rate_limit,
)


def _scope(headers: list[tuple[bytes, bytes]]) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/unprotected",
        "raw_path": b"/unprotected",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }


@pytest.mark.asyncio
async def test_redis_rest_limit_blocks_after_policy_limit_without_exposing_ip() -> None:
    responses = iter(({"result": [1, 60]}, {"result": [11, 42]}))
    executor = AsyncMock(side_effect=lambda _command: next(responses))
    limiter = RedisRestRateLimiter("https://redis.example", "secret", executor=executor)
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    allowed = await limiter.check(policy, "203.0.113.9")
    denied = await limiter.check(policy, "203.0.113.9")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.retry_after_seconds == 42
    command = executor.await_args.args[0]
    assert "203.0.113.9" not in str(command)
    assert command[0] == "EVAL"


@pytest.mark.asyncio
async def test_missing_redis_configuration_is_explicitly_fail_open() -> None:
    executor = AsyncMock()
    limiter = RedisRestRateLimiter("", "", executor=executor)

    result = await limiter.check(ROUTE_POLICIES["/api/v1/auth/login"], "unknown")

    assert result.allowed is True
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_failure_fails_open_without_leaking_backend_details() -> None:
    executor = AsyncMock(side_effect=httpx.ConnectError("unavailable"))
    limiter = RedisRestRateLimiter("https://redis.example", "secret", executor=executor)

    result = await limiter.check(ROUTE_POLICIES["/api/v1/auth/login"], "203.0.113.9")

    assert result.allowed is True


@pytest.mark.asyncio
async def test_unexpected_redis_error_still_fails_open() -> None:
    executor = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
    limiter = RedisRestRateLimiter("https://redis.example", "secret", executor=executor)

    result = await limiter.check(ROUTE_POLICIES["/api/v1/auth/login"], "203.0.113.9")

    assert result.allowed is True


def test_middleware_returns_safe_429_and_413_before_endpoint() -> None:
    async def executor(_command: list[object]) -> object:
        return {"result": [11, 30]}

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RedisRestRateLimiter("https://redis.example", "secret", executor=executor),
        max_request_body_bytes=10,
        trust_proxy_headers=False,
    )

    @app.post("/api/v1/auth/login")
    async def login() -> dict[str, bool]:
        return {"reached": True}

    with TestClient(app) as client:
        limited = client.post("/api/v1/auth/login", content=b"small")
        oversized = client.post("/api/v1/auth/login", content=b"this body is too large")

    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "30"
    assert limited.json()["errors"] == [
        {"code": "RATE_LIMITED", "scope": "auth.login", "retry_after_seconds": 30}
    ]
    assert oversized.status_code == 413
    assert oversized.json()["errors"] == [{"code": "REQUEST_TOO_LARGE"}]


def test_middleware_defers_webhook_bucket_until_the_signature_layer() -> None:
    executor = AsyncMock(return_value={"result": [241, 15]})
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RedisRestRateLimiter("https://redis.example", "secret", executor=executor),
        max_request_body_bytes=1024,
        trust_proxy_headers=False,
    )

    @app.post("/api/v1/sales/checkout/mercado-pago/webhook")
    async def webhook() -> dict[str, bool]:
        return {"signature_layer_reached": True}

    with TestClient(app) as client:
        response = client.post("/api/v1/sales/checkout/mercado-pago/webhook", content=b"{}")

    assert response.status_code == 200
    executor.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [(b"transfer-encoding", b"chunked")],
        [(b"content-length", b"3")],
    ],
)
async def test_asgi_body_limit_rejects_chunked_or_underdeclared_body_before_fastapi(
    headers: list[tuple[bytes, bytes]],
) -> None:
    events = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.request", "body": b"456", "more_body": False},
    ]
    sent: list[dict] = []
    reached = False

    async def receive() -> dict:
        return events.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        nonlocal reached
        reached = True
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware = RateLimitMiddleware(
        downstream,
        limiter=RedisRestRateLimiter("", ""),
        max_request_body_bytes=5,
        trust_proxy_headers=False,
    )

    await middleware(_scope(headers), receive, send)

    assert reached is False
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_webhook_limit_is_deferred_until_signature_layer_and_uses_own_scope() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                rate_limiter=RedisRestRateLimiter(
                    "https://redis.example",
                    "secret",
                    executor=AsyncMock(return_value={"result": [241, 15]}),
                ),
                rate_limit_trust_proxy_headers=False,
            )
        ),
        client=SimpleNamespace(host="198.51.100.2"),
        headers={},
    )

    response = await enforce_verified_webhook_rate_limit(request)

    assert response is not None
    assert response.status_code == 429
    assert b"webhook.mercado_pago" in response.body


def test_client_ip_only_trusts_forwarded_header_when_explicitly_enabled() -> None:
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.8"),
        headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"},
    )

    assert client_ip(request, trust_proxy_headers=False) == "10.0.0.8"
    assert client_ip(request, trust_proxy_headers=True) == "10.0.0.1"


def _req(headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.8"), headers=headers)


def test_client_ip_uses_rightmost_forwarded_value() -> None:
    request = _req({"x-forwarded-for": "1.1.1.1, 203.0.113.9, 198.51.100.7"})

    assert client_ip(request, trust_proxy_headers=True) == "198.51.100.7"


def test_client_ip_configured_header_takes_precedence() -> None:
    request = _req({"x-forwarded-for": "1.1.1.1", "x-real-ip": "203.0.113.9"})

    assert client_ip(request, True, "X-Real-IP") == "203.0.113.9"
    assert client_ip(request, True, "x-missing") == "10.0.0.8"


def test_client_ip_ignores_all_headers_when_trust_flag_is_false() -> None:
    request = _req({"x-forwarded-for": "1.1.1.1", "x-real-ip": "203.0.113.9"})

    assert client_ip(request, False, "x-real-ip") == "10.0.0.8"


def test_missing_redis_configuration_warns_once_at_startup(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="ecommerce_atacadao.rate_limit"):
        RedisRestRateLimiter("", "")

    assert [r.getMessage() for r in caplog.records] == [
        "rate_limit_disabled reason=missing_redis_configuration"
    ]


def test_missing_redis_configuration_is_error_in_production(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="ecommerce_atacadao.rate_limit"):
        RedisRestRateLimiter("", "", environment="production")

    assert caplog.records[0].levelno == logging.ERROR


@pytest.mark.asyncio
async def test_failure_cooldown_skips_redis_and_logs_once(caplog) -> None:
    now = [100.0]
    executor = AsyncMock(side_effect=httpx.ConnectError("down"))
    limiter = RedisRestRateLimiter(
        "https://redis.example",
        "secret",
        executor=executor,
        failure_cooldown_seconds=30,
        clock=lambda: now[0],
    )
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    with caplog.at_level(logging.WARNING, logger="ecommerce_atacadao.rate_limit"):
        for _ in range(3):
            assert (await limiter.check(policy, "203.0.113.9")).allowed is True
        assert executor.await_count == 1
        now[0] += 31
        await limiter.check(policy, "203.0.113.9")

    assert executor.await_count == 2
    assert sum("rate_limit_fail_open" in r.getMessage() for r in caplog.records) == 2


@pytest.mark.asyncio
async def test_http_client_is_reused_and_closed(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict:
            return {"result": [1, 60]}

    class FakeClient:
        def __init__(self, **_kw) -> None:
            calls.append("init")

        async def post(self, *_a, **_kw) -> FakeResponse:
            return FakeResponse()

        async def aclose(self) -> None:
            calls.append("close")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    limiter = RedisRestRateLimiter("https://redis.example", "secret")
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    await limiter.check(policy, "1.1.1.1")
    await limiter.check(policy, "1.1.1.1")
    await limiter.aclose()

    assert calls == ["init", "close"]


# --- Redis TCP -------------------------------------------------------------

TCP_URL = "rediss://default:s3cr3t-pass@redis-host.example.com:6380"


@pytest.mark.asyncio
async def test_tcp_limit_blocks_after_policy_limit_via_fake_executor() -> None:
    responses = iter(([1, 60], [11, 42]))
    executor = AsyncMock(side_effect=lambda _command: next(responses))
    limiter = RedisTcpRateLimiter(TCP_URL, executor=executor)
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    allowed = await limiter.check(policy, "203.0.113.9")
    denied = await limiter.check(policy, "203.0.113.9")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.retry_after_seconds == 42
    command = executor.await_args.args[0]
    assert command[0] == "EVAL"
    assert command[1] == RedisRestRateLimiter._COUNTER_SCRIPT
    assert "203.0.113.9" not in str(command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        redis_exceptions.ConnectionError("down"),
        OSError("refused"),
        asyncio.TimeoutError(),
        RuntimeError("Event loop is closed"),
    ],
)
async def test_tcp_failure_fails_open_with_cooldown_and_single_log(error, caplog) -> None:
    now = [100.0]
    executor = AsyncMock(side_effect=error)
    limiter = RedisTcpRateLimiter(
        TCP_URL, executor=executor, failure_cooldown_seconds=30, clock=lambda: now[0]
    )
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    with caplog.at_level(logging.WARNING, logger="ecommerce_atacadao.rate_limit"):
        for _ in range(3):
            assert (await limiter.check(policy, "203.0.113.9")).allowed is True
        assert executor.await_count == 1
        now[0] += 31
        await limiter.check(policy, "203.0.113.9")

    assert executor.await_count == 2
    assert sum("rate_limit_fail_open" in r.getMessage() for r in caplog.records) == 2
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "s3cr3t-pass" not in text and "redis-host" not in text and "203.0.113.9" not in text


@pytest.mark.asyncio
async def test_tcp_client_is_lazy_reused_discarded_on_error_and_closed(monkeypatch) -> None:
    created: list[object] = []

    class FakeRedis:
        def __init__(self, fail: bool) -> None:
            self.fail = fail
            self.closed = False

        async def eval(self, *_a):
            if self.fail:
                raise redis_exceptions.ConnectionError("down")
            return [1, 60]

        async def aclose(self, **_kw) -> None:
            self.closed = True

    def fake_redis(*, connection_pool, **_kw):
        kw = connection_pool.connection_kwargs
        assert connection_pool.max_connections == 10
        assert kw["socket_connect_timeout"] <= 1.0 and kw["socket_timeout"] <= 1.0
        assert kw["health_check_interval"] > 0
        client = FakeRedis(fail=len(created) == 0)
        created.append(client)
        return client

    monkeypatch.setattr("src.core.rate_limit.Redis", fake_redis)
    now = [0.0]
    limiter = RedisTcpRateLimiter(TCP_URL, failure_cooldown_seconds=10, clock=lambda: now[0])
    policy = ROUTE_POLICIES["/api/v1/auth/login"]
    assert created == []

    await limiter.check(policy, "1.1.1.1")  # falha: descarta o client
    await asyncio.sleep(0)
    assert created[0].closed is True
    now[0] += 11
    await limiter.check(policy, "1.1.1.1")
    await limiter.check(policy, "1.1.1.1")
    assert len(created) == 2
    await limiter.aclose()
    assert created[1].closed is True


def _settings(monkeypatch, **env):
    for key in ("RATE_LIMIT_REDIS_URL", "STORAGE_REDIS_URL", "RATE_LIMIT_REDIS_REST_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://ci:ci@localhost:5432/ci",
        "SECRET_KEY": "x",
        "REFRESH_SECRET_KEY": "y",
        "MELHOR_ENVIO_TOKEN": "t",
        "MELHOR_ENVIO_USER_AGENT": "a",
        "STORE_ORIGIN_ZIP_CODE": "01001000",
        **env,
    }.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_settings_accept_storage_redis_url_alias(monkeypatch) -> None:
    assert _settings(monkeypatch, STORAGE_REDIS_URL=TCP_URL).RATE_LIMIT_REDIS_URL == TCP_URL
    assert _settings(monkeypatch, RATE_LIMIT_REDIS_URL=TCP_URL).RATE_LIMIT_REDIS_URL == TCP_URL
    assert _settings(monkeypatch).RATE_LIMIT_REDIS_URL == ""


def test_backend_selection_prefers_tcp_over_rest(monkeypatch) -> None:
    from src import main

    both = _settings(
        monkeypatch,
        STORAGE_REDIS_URL=TCP_URL,
        RATE_LIMIT_REDIS_REST_URL="https://r.example",
        RATE_LIMIT_REDIS_REST_TOKEN="tok",
    )
    monkeypatch.setattr(main, "settings", both)
    assert isinstance(main.build_rate_limiter(), RedisTcpRateLimiter)

    rest = _settings(
        monkeypatch,
        RATE_LIMIT_REDIS_REST_URL="https://r.example",
        RATE_LIMIT_REDIS_REST_TOKEN="tok",
    )
    monkeypatch.setattr(main, "settings", rest)
    limiter = main.build_rate_limiter()
    assert isinstance(limiter, RedisRestRateLimiter) and limiter.enabled

    monkeypatch.setattr(main, "settings", _settings(monkeypatch))
    assert main.build_rate_limiter().enabled is False


@pytest.mark.asyncio
async def test_tcp_hanging_operation_fails_open_within_timeout() -> None:
    async def hang(_command):
        await asyncio.sleep(30)

    class HangingRedis:
        async def eval(self, *_a):
            await hang(None)

        async def aclose(self, **_kw) -> None: ...

    limiter = RedisTcpRateLimiter(TCP_URL, timeout_seconds=0.1)
    limiter._client = HangingRedis()  # type: ignore[assignment]
    started = time.monotonic()
    result = await limiter.check(ROUTE_POLICIES["/api/v1/auth/login"], "1.1.1.1")

    assert result.allowed is True
    assert time.monotonic() - started < 0.5
    assert limiter._client is None
    await limiter.aclose()
    assert not limiter._close_tasks


@pytest.mark.asyncio
async def test_tcp_pool_exhaustion_does_not_discard_client_nor_open_cooldown(caplog) -> None:
    class BusyRedis:
        calls = 0

        async def eval(self, *_a):
            BusyRedis.calls += 1
            raise redis_exceptions.ConnectionError("No connection available.")

        async def aclose(self, **_kw) -> None: ...

    limiter = RedisTcpRateLimiter(TCP_URL, clock=lambda: 0.0)
    client = BusyRedis()
    limiter._client = client  # type: ignore[assignment]
    policy = ROUTE_POLICIES["/api/v1/auth/login"]

    with caplog.at_level(logging.WARNING, logger="ecommerce_atacadao.rate_limit"):
        for _ in range(3):
            assert (await limiter.check(policy, "1.1.1.1")).allowed is True

    assert BusyRedis.calls == 3  # sem cooldown global
    assert limiter._client is client  # client preservado
    messages = [r.getMessage() for r in caplog.records]
    assert sum("rate_limit_pool_exhausted" in m for m in messages) == 1
    assert not any("rate_limit_fail_open" in m for m in messages)


def test_tcp_uses_small_blocking_pool_without_internal_retries(monkeypatch) -> None:
    limiter = RedisTcpRateLimiter(TCP_URL)
    pool = limiter._get_client().connection_pool
    assert pool.max_connections == 10
    assert pool.timeout == 0.2
    assert pool.connection_kwargs.get("retry_on_timeout") is False
