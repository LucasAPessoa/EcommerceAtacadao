"""Tema da loja: GET público, PUT/lista admin (singleton `store_settings`)."""

from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import API_V1_PREFIX, auth_headers

PUBLIC = f"{API_V1_PREFIX}/store/theme"
ADMIN_THEME = f"{API_V1_PREFIX}/admin/store/theme"
ADMIN_THEMES = f"{API_V1_PREFIX}/admin/store/themes"


async def _clear(db: AsyncEngine) -> None:
    async with db.begin() as conn:
        await conn.execute(text("DELETE FROM store_settings"))


@pytest_asyncio.fixture
async def clean_theme(db: AsyncEngine) -> AsyncIterator[None]:
    await _clear(db)
    yield
    await _clear(db)


async def test_default_without_record(client: httpx.AsyncClient, clean_theme: None) -> None:
    resp = await client.get(PUBLIC)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["theme"] == "gondola"
    assert data["brand_color"] is None
    assert data["updated_at"] is None


async def test_put_then_get_and_overwrite(
    client: httpx.AsyncClient, admin_token: str, clean_theme: None
) -> None:
    headers = auth_headers(admin_token)

    put = await client.put(
        ADMIN_THEME, json={"theme": "gondola", "brand_color": "#1d6b57"}, headers=headers
    )
    assert put.status_code == 200
    assert put.json()["data"]["brand_color"] == "#1D6B57"

    got = (await client.get(PUBLIC)).json()["data"]
    assert got["theme"] == "gondola"
    assert got["brand_color"] == "#1D6B57"
    assert got["updated_at"] is not None

    again = await client.put(
        ADMIN_THEME, json={"theme": "gondola", "brand_color": None}, headers=headers
    )
    assert again.status_code == 200
    assert (await client.get(PUBLIC)).json()["data"]["brand_color"] is None


async def test_invalid_theme_is_422(client: httpx.AsyncClient, admin_token: str) -> None:
    resp = await client.put(
        ADMIN_THEME,
        json={"theme": "inexistente", "brand_color": None},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 422


@pytest.mark.parametrize("color", ["1D6B57", "#12345", "#GGGGGG", "#1D6B577", "verde"])
async def test_invalid_color_is_422(
    client: httpx.AsyncClient, admin_token: str, color: str
) -> None:
    resp = await client.put(
        ADMIN_THEME,
        json={"theme": "gondola", "brand_color": color},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 422


async def test_list_themes(client: httpx.AsyncClient, admin_token: str) -> None:
    resp = await client.get(ADMIN_THEMES, headers=auth_headers(admin_token))

    assert resp.status_code == 200
    themes = resp.json()["data"]
    assert {"key": "gondola", "name": "Gôndola"}.items() <= themes[0].items()
    assert themes[0]["description"]


async def test_put_without_token_is_401(client: httpx.AsyncClient) -> None:
    resp = await client.put(ADMIN_THEME, json={"theme": "gondola", "brand_color": None})

    assert resp.status_code == 401


async def test_put_as_user_is_403(client: httpx.AsyncClient, user_token: str) -> None:
    resp = await client.put(
        ADMIN_THEME,
        json={"theme": "gondola", "brand_color": None},
        headers=auth_headers(user_token),
    )

    assert resp.status_code == 403
