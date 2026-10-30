import json
import logging
from typing import Any, Callable, Optional

import httpx
import pytest

from src.integrations.bling.client import BlingClient, RateLimiter
from src.integrations.bling.errors import (
    BlingRateLimitedError,
    BlingReconnectRequiredError,
    BlingRejectedError,
    BlingUnavailableError,
)

SECRET_TOKEN = "tok-SECRET-abc123"
NEW_TOKEN = "tok-NEW-xyz789"


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[Optional[str]] = []
        self.marked: list[str] = []

    async def get_token(self, stale_token: Optional[str] = None) -> str:
        self.calls.append(stale_token)
        return SECRET_TOKEN if stale_token is None else NEW_TOKEN

    async def mark_reconnect_required(self, reason: str) -> None:
        self.marked.append(reason)


class Harness:
    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.provider = FakeProvider()

        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        async def limiter_sleep(seconds: float) -> None:
            pass  # espera do limitador não faz parte do backoff medido

        self.client = BlingClient(
            self.provider,
            transport=httpx.MockTransport(wrapped),
            limiter=RateLimiter(clock=lambda: 1e9, sleep=limiter_sleep),
            sleep=sleep,
            rng=lambda: 0.0,
            base_url="http://bling.test/Api/v3",
        )


def _seq(*responses: Any) -> Callable[[httpx.Request], httpx.Response]:
    items = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(item, Exception):
            raise item
        return item

    return handler


async def test_success_sends_bearer_params_and_returns_dict() -> None:
    h = Harness(_seq(httpx.Response(200, json={"data": [1]})))

    body = await h.client.request("GET", "/produtos", params={"pagina": 2})

    assert body == {"data": [1]}
    assert h.requests[0].headers["authorization"] == f"Bearer {SECRET_TOKEN}"
    assert h.requests[0].url.params["pagina"] == "2"
    assert h.sleeps == []


async def test_empty_body_returns_empty_dict() -> None:
    h = Harness(_seq(httpx.Response(204)))

    assert await h.client.request("DELETE", "/x") == {}


async def test_retry_backoff_exponential_then_success() -> None:
    h = Harness(
        _seq(
            httpx.Response(503),
            httpx.Response(500),
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"ok": True}),
        )
    )

    assert await h.client.request("GET", "/x") == {"ok": True}
    assert h.sleeps == [1.0, 2.0, 4.0]
    assert len(h.requests) == 4


async def test_retries_exhausted_503_is_unavailable_with_waits_1_2_4_8() -> None:
    h = Harness(_seq(httpx.Response(503)))

    with pytest.raises(BlingUnavailableError):
        await h.client.request("GET", "/x")

    assert h.sleeps == [1.0, 2.0, 4.0, 8.0]
    assert len(h.requests) == 5


async def test_retries_exhausted_429_is_rate_limited() -> None:
    h = Harness(_seq(httpx.Response(429)))

    with pytest.raises(BlingRateLimitedError):
        await h.client.request("GET", "/x")


async def test_network_failure_exhausted_is_unavailable() -> None:
    h = Harness(_seq(httpx.ReadTimeout("t")))

    with pytest.raises(BlingUnavailableError):
        await h.client.request("GET", "/x")


async def test_jitter_adds_up_to_25_percent() -> None:
    h = Harness(_seq(httpx.Response(503), httpx.Response(200, json={})))
    h.client.rng = lambda: 1.0

    await h.client.request("GET", "/x")

    assert h.sleeps == [1.25]


async def test_retry_after_is_honored_when_larger() -> None:
    h = Harness(
        _seq(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={}))
    )

    await h.client.request("GET", "/x")

    assert h.sleeps == [7.0]


@pytest.mark.parametrize("status", [400, 403, 404, 422])
async def test_4xx_is_not_retried_and_is_classified(status: int) -> None:
    body = {"error": {"type": "VALIDATION_ERROR", "message": "campo inválido"}}
    h = Harness(_seq(httpx.Response(status, json=body)))

    with pytest.raises(BlingRejectedError) as exc:
        await h.client.request("POST", "/x", json={"a": 1})

    assert exc.value.status == status
    assert exc.value.error_type == "VALIDATION_ERROR"
    assert exc.value.message == "campo inválido"
    assert len(h.requests) == 1 and h.sleeps == []


async def test_401_refreshes_once_and_repeats_with_new_token() -> None:
    h = Harness(_seq(httpx.Response(401), httpx.Response(200, json={"ok": 1})))

    assert await h.client.request("GET", "/x") == {"ok": 1}

    assert h.provider.calls == [None, SECRET_TOKEN]
    assert h.requests[1].headers["authorization"] == f"Bearer {NEW_TOKEN}"
    assert h.provider.marked == []


async def test_401_after_refresh_requires_reconnect() -> None:
    h = Harness(_seq(httpx.Response(401)))

    with pytest.raises(BlingReconnectRequiredError):
        await h.client.request("GET", "/x")

    assert len(h.requests) == 2
    assert h.provider.marked == ["api_unauthorized"]


async def test_limiter_spaces_requests_to_2_5_per_second() -> None:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    limiter = RateLimiter(rate=2.5, clock=lambda: 100.0, sleep=sleep)

    for _ in range(4):
        await limiter.acquire()

    assert sleeps == pytest.approx([0.4, 0.8, 1.2])


async def test_limiter_does_not_wait_when_idle() -> None:
    now = [0.0]
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    limiter = RateLimiter(rate=2.5, clock=lambda: now[0], sleep=sleep)
    await limiter.acquire()
    now[0] = 10.0
    await limiter.acquire()

    assert sleeps == []


async def test_no_token_in_logs_or_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    h = Harness(_seq(httpx.Response(503), httpx.Response(401), httpx.Response(401)))
    with pytest.raises(BlingReconnectRequiredError) as exc1:
        await h.client.request("GET", "/x")
    h2 = Harness(_seq(httpx.Response(503)))
    with pytest.raises(BlingUnavailableError) as exc2:
        await h2.client.request("GET", "/x")
    h3 = Harness(_seq(httpx.Response(400, json={"error": {"type": "T", "message": "m"}})))
    with pytest.raises(BlingRejectedError) as exc3:
        await h3.client.request("GET", "/x")

    haystack = caplog.text + "".join(str(e.value) + repr(e.value) for e in (exc1, exc2, exc3))
    assert SECRET_TOKEN not in haystack and NEW_TOKEN not in haystack
    assert "bling_request_retry" in caplog.text


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_non_idempotent_not_retried_on_5xx(method: str) -> None:
    h = Harness(_seq(httpx.Response(503), httpx.Response(200, json={})))

    with pytest.raises(BlingUnavailableError):
        await h.client.request(method, "/x", json={"a": 1})

    assert len(h.requests) == 1 and h.sleeps == []


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_non_idempotent_not_retried_after_request_sent(method: str) -> None:
    h = Harness(_seq(httpx.ReadTimeout("t"), httpx.Response(200, json={})))

    with pytest.raises(BlingUnavailableError):
        await h.client.request(method, "/x")

    assert len(h.requests) == 1


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_non_idempotent_retried_on_429_and_connect_error(method: str) -> None:
    h = Harness(
        _seq(
            httpx.Response(429),
            httpx.ConnectError("c"),
            httpx.ConnectTimeout("c"),
            httpx.Response(200, json={"ok": 1}),
        )
    )

    assert await h.client.request(method, "/x") == {"ok": 1}
    assert h.sleeps == [1.0, 2.0, 4.0]


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_idempotent_still_retried_on_5xx_and_read_timeout(method: str) -> None:
    h = Harness(_seq(httpx.Response(500), httpx.ReadTimeout("t"), httpx.Response(200, json={})))

    await h.client.request(method, "/x")

    assert len(h.requests) == 3


# ------------------------------------------------------------------ vínculos produto-loja (008)

STORE_LINK_RAW: dict[str, Any] = {
    "id": 1029221462,
    "codigo": "ARR-5",
    "preco": 100,
    "precoPromocional": 0,
    "produto": {"id": 16621836105},
    "loja": {"id": 206347377},
    "fornecedorLoja": {"id": 0},
    "marcaLoja": {"id": 0},
    "categoriasProdutos": [],
}


async def test_list_store_links_page_sends_store_filter_and_normalizes() -> None:
    from src.integrations.bling.catalog import BlingCatalogClient

    h = Harness(_seq(httpx.Response(200, json={"data": [STORE_LINK_RAW]})))

    links, has_more = await BlingCatalogClient(h.client).list_store_links_page(206347377, 3)

    assert (links[0].id, links[0].product_id, links[0].store_id) == (
        1029221462,
        16621836105,
        206347377,
    )
    assert str(links[0].price) == "100.00" and str(links[0].promo_price) == "0.00"
    assert has_more is False
    request = h.requests[0]
    assert request.url.path.endswith("/produtos/lojas")
    assert request.url.params["idLoja"] == "206347377" and request.url.params["pagina"] == "3"


async def test_put_store_link_resends_read_body_changing_only_price() -> None:
    """FR-013: o PUT reenvia o vínculo lido e só troca `preco`."""
    from decimal import Decimal

    from src.integrations.bling.catalog import BlingCatalogClient, store_link_body_with_price

    h = Harness(
        _seq(
            httpx.Response(200, json={"data": STORE_LINK_RAW}),
            httpx.Response(200, json={}),
        )
    )
    catalog = BlingCatalogClient(h.client)

    link = await catalog.get_store_link(1029221462)
    await catalog.put_store_link(link.id, store_link_body_with_price(link, Decimal("27.90")))

    sent = json.loads(h.requests[1].content)
    assert h.requests[1].method == "PUT"
    assert h.requests[1].url.path.endswith("/produtos/lojas/1029221462")
    assert sent["preco"] == 27.9
    assert {k: v for k, v in sent.items() if k != "preco"} == {
        k: v for k, v in STORE_LINK_RAW.items() if k != "preco"
    }
    assert link.raw == STORE_LINK_RAW  # a leitura não foi alterada


async def test_put_store_link_retries_but_create_does_not_retry_on_5xx() -> None:
    from src.integrations.bling.catalog import BlingCatalogClient

    put = Harness(_seq(httpx.Response(503), httpx.Response(200, json={})))
    await BlingCatalogClient(put.client).put_store_link(1, {"preco": 1})
    assert len(put.requests) == 2

    post = Harness(_seq(httpx.Response(503), httpx.Response(200, json={"data": {"id": 9}})))
    with pytest.raises(BlingUnavailableError):
        await BlingCatalogClient(post.client).create_store_link({"preco": 1})
    assert len(post.requests) == 1 and post.sleeps == []


async def test_create_store_link_returns_id() -> None:
    from src.integrations.bling.catalog import BlingCatalogClient

    h = Harness(_seq(httpx.Response(201, json={"data": {"id": 77}})))

    assert await BlingCatalogClient(h.client).create_store_link({"preco": 1}) == 77
    assert h.requests[0].method == "POST"
