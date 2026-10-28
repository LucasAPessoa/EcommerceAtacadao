"""T006: toda rota /admin/* exige token (401) e papel admin (403), antes de ler dados.

A lista ``ROUTES`` cresce a cada história do portal.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import API_V1_PREFIX, auth_headers

ADMIN = f"{API_V1_PREFIX}/admin"
SOME_ID = uuid.uuid4()

ROUTES = [
    ("GET", f"{ADMIN}/products"),
    ("GET", f"{ADMIN}/products/{SOME_ID}"),
    ("PATCH", f"{ADMIN}/products/{SOME_ID}/presentation"),
    ("PATCH", f"{ADMIN}/products/presentation"),
    ("GET", f"{ADMIN}/orders"),
    ("GET", f"{ADMIN}/orders/{SOME_ID}"),
    ("GET", f"{ADMIN}/dashboard/summary"),
    ("GET", f"{ADMIN}/bling/pending"),
    ("GET", f"{ADMIN}/moderation/reviews"),
    ("GET", f"{ADMIN}/moderation/questions"),
    ("GET", f"{ADMIN}/store/themes"),
    ("PUT", f"{ADMIN}/store/theme"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_no_token_gets_401(client: httpx.AsyncClient, method: str, path: str) -> None:
    resp = await client.request(method, path)

    assert resp.status_code == 401


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_regular_user_gets_403(
    client: httpx.AsyncClient, user_token: str, method: str, path: str
) -> None:
    resp = await client.request(method, path, headers=auth_headers(user_token))

    assert resp.status_code == 403


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_refresh_token_is_not_accepted(
    client: httpx.AsyncClient, admin_refresh_token: str, method: str, path: str
) -> None:
    resp = await client.request(method, path, headers=auth_headers(admin_refresh_token))

    assert resp.status_code in (401, 403)
