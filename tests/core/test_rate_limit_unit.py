import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.rate_limit import (
    ROUTE_POLICIES,
    RateLimitMiddleware,
    RedisRestRateLimiter,
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
