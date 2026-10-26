"""`main_image_url` na lista e no detalhe do produto (back #54). Exige scripts/run_api_tests.sh."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import API_V1_PREFIX

CATALOG = f"{API_V1_PREFIX}/catalog"
# (ativa, [(url, is_main)]) por variação, na ordem de criação.
Spec = List[Tuple[bool, List[Tuple[str, bool]]]]


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    url = os.environ.get("DATABASE_URL")
    assert url, "DATABASE_URL ausente: rode via scripts/run_api_tests.sh"
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def make_product(db: AsyncEngine) -> AsyncIterator[Any]:
    created: List[uuid.UUID] = []

    async def make(spec: Spec) -> str:
        pid = uuid.uuid4()
        code = f"MI-{pid.hex[:12]}"
        base = datetime(2030, 1, 1)
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO products (id, name, code, is_active, created_at, updated_at)"
                    " VALUES (:id, 'Produto imagem', :code, true, :t, :t)"
                ),
                {"id": pid, "code": code, "t": base},
            )
            for n, (active, imgs) in enumerate(spec):
                vid = uuid.uuid4()
                t = base + timedelta(minutes=n)
                await conn.execute(
                    text(
                        "INSERT INTO product_variants (id, product_id, bling_sku, variation_name,"
                        " base_price, stock_quantity, is_active, created_at, updated_at)"
                        " VALUES (:id, :p, :sku, 'v', 10, 1, :a, :t, :t)"
                    ),
                    {"id": vid, "p": pid, "sku": f"{code}-{n}", "a": active, "t": t},
                )
                for k, (url, main) in enumerate(imgs):
                    await conn.execute(
                        text(
                            "INSERT INTO product_images (id, variant_id, image_url, is_main,"
                            " created_at, updated_at) VALUES (:id, :v, :u, :m, :t, :t)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "v": vid,
                            "u": url,
                            "m": main,
                            "t": t + timedelta(seconds=k),
                        },
                    )
        created.append(pid)
        return code

    yield make
    async with db.begin() as conn:
        for pid in created:
            await conn.execute(
                text(
                    "DELETE FROM product_images WHERE variant_id IN"
                    " (SELECT id FROM product_variants WHERE product_id = :p)"
                ),
                {"p": pid},
            )
            await conn.execute(
                text("DELETE FROM product_variants WHERE product_id = :p"), {"p": pid}
            )
            await conn.execute(text("DELETE FROM products WHERE id = :p"), {"p": pid})


async def _urls(client: httpx.AsyncClient, code: str) -> Dict[str, Optional[str]]:
    detail = await client.get(f"{CATALOG}/products/code/{code}")
    assert detail.status_code == 200, detail.text
    body = detail.json()["data"]
    by_id = await client.get(f"{CATALOG}/products/{body['id']}")
    assert by_id.status_code == 200, by_id.text
    listing = await client.get(f"{CATALOG}/products/", params={"limit": 500})
    row = next(p for p in listing.json()["data"] if p["code"] == code)
    return {
        "code": body["main_image_url"],
        "id": by_id.json()["data"]["main_image_url"],
        "list": row["main_image_url"],
    }


async def _assert_all(client: httpx.AsyncClient, code: str, expected: Optional[str]) -> None:
    assert await _urls(client, code) == {"code": expected, "id": expected, "list": expected}


@pytest.mark.asyncio
async def test_main_image_of_first_active_variant(client: httpx.AsyncClient, make_product):
    code = await make_product(
        [
            (True, [("http://x/a1.jpg", False), ("http://x/a2.jpg", True)]),
            (True, [("http://x/b.jpg", True)]),
        ]
    )
    await _assert_all(client, code, "http://x/a2.jpg")


@pytest.mark.asyncio
async def test_falls_back_to_first_image_without_main(client: httpx.AsyncClient, make_product):
    code = await make_product(
        [(True, []), (True, [("http://x/b1.jpg", False), ("http://x/b2.jpg", False)])]
    )
    await _assert_all(client, code, "http://x/b1.jpg")


@pytest.mark.asyncio
async def test_without_images_is_null(client: httpx.AsyncClient, make_product):
    await _assert_all(client, await make_product([(True, [])]), None)


@pytest.mark.asyncio
async def test_image_only_on_inactive_variant_is_null(client: httpx.AsyncClient, make_product):
    code = await make_product([(False, [("http://x/i.jpg", True)]), (True, [])])
    await _assert_all(client, code, None)
