"""US3: visibilidade e destaque (lote), listagem pública e invariantes de compra/preço."""

from __future__ import annotations

import os
import uuid
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.models.sales import Cart
from src.repositories.sales.cart_repository import CartRepository
from src.repositories.sales.order_repository import OrderRepository
from src.services.sales.checkout_service import CheckoutService
from tests.admin.conftest import Seeder
from tests.conftest import API_V1_PREFIX, auth_headers

ADMIN = f"{API_V1_PREFIX}/admin/products"
PUBLIC = f"{API_V1_PREFIX}/catalog/products"


async def _batch(client: httpx.AsyncClient, token: str, body: dict[str, Any]) -> httpx.Response:
    return await client.patch(f"{ADMIN}/presentation", json=body, headers=auth_headers(token))


async def _public_ids(client: httpx.AsyncClient, **params: Any) -> list[str]:
    resp = await client.get(PUBLIC + "/", params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    return [p["id"] for p in resp.json()["data"]]


async def _count_rows(db: AsyncEngine, ids: list[uuid.UUID]) -> int:
    async with db.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM product_site_presentation WHERE product_id = ANY(:ids)"),
            {"ids": ids},
        )
        return result.scalar_one()


class TestBatch:
    async def test_hide_three_products_in_one_call(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        cat = await seed.category("C")
        pids = [await seed.product(f"P{n}", categories=(cat,)) for n in range(4)]
        assert len(await _public_ids(client, category_id=str(cat))) == 4

        resp = await _batch(
            client, admin_token, {"product_ids": [str(p) for p in pids[:3]], "visible": False}
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"updated": 3}
        assert await _public_ids(client, category_id=str(cat)) == [str(pids[3])]
        assert str(pids[0]) not in await _public_ids(client)
        # Detalhe direto continua respondendo para oculto.
        detail = await client.get(f"{PUBLIC}/{pids[0]}")
        assert detail.status_code == 200
        code = detail.json()["data"]["code"]
        assert (await client.get(f"{PUBLIC}/code/{code}")).status_code == 200
        admin = await client.get(f"{ADMIN}/{pids[0]}", headers=auth_headers(admin_token))
        assert admin.json()["data"]["presentation"]["visible"] is False

        resp = await _batch(
            client, admin_token, {"product_ids": [str(p) for p in pids[:3]], "visible": True}
        )

        assert len(await _public_ids(client, category_id=str(cat))) == 4

    async def test_missing_ids_return_404_listing_them_and_write_nothing(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        real = await seed.product("Real")
        deleted = await seed.product("Gone", deleted=True)
        ghost = uuid.uuid4()

        resp = await _batch(
            client,
            admin_token,
            {"product_ids": [str(real), str(ghost), str(deleted)], "visible": False},
        )

        assert resp.status_code == 404
        assert str(ghost) in resp.json()["detail"] and str(deleted) in resp.json()["detail"]
        assert str(real) not in resp.json()["detail"]
        assert await _count_rows(db, [real]) == 0
        assert str(real) in await _public_ids(client)

    async def test_featured_lists_only_featured_and_visible(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        cat = await seed.category("C")
        star = await seed.product("Star", categories=(cat,))
        hidden_star = await seed.product("HiddenStar", categories=(cat,))
        plain = await seed.product("Plain", categories=(cat,))
        await _batch(client, admin_token, {"product_ids": [str(star)], "featured": True})
        await _batch(
            client,
            admin_token,
            {"product_ids": [str(hidden_star)], "featured": True, "visible": False},
        )

        featured = await _public_ids(client, category_id=str(cat), featured="true")
        everything = await _public_ids(client, category_id=str(cat))
        not_featured_filter = await _public_ids(client, category_id=str(cat), featured="false")

        assert featured == [str(star)]
        assert sorted(everything) == sorted([str(star), str(plain)])
        assert sorted(not_featured_filter) == sorted(everything)

    async def test_flags_are_independent(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        pid = await seed.product("P")
        await _batch(client, admin_token, {"product_ids": [str(pid)], "visible": False})

        await _batch(client, admin_token, {"product_ids": [str(pid), str(pid)], "featured": True})

        resp = await client.get(f"{ADMIN}/{pid}", headers=auth_headers(admin_token))
        pres = resp.json()["data"]["presentation"]
        assert (pres["visible"], pres["featured"]) == (False, True)
        assert pres["updated_by"] is not None

    @pytest.mark.parametrize(
        "body",
        [
            {"product_ids": [], "visible": False},
            {"product_ids": [str(uuid.uuid4()) for _ in range(101)], "visible": False},
            {"product_ids": [str(uuid.uuid4())]},
            {"product_ids": [str(uuid.uuid4())], "visible": None, "featured": None},
            {"product_ids": [str(uuid.uuid4())], "visible": False, "name": "x"},
            {"visible": False},
        ],
    )
    async def test_invalid_payload_is_422(
        self, client: httpx.AsyncClient, admin_token: str, body: dict[str, Any]
    ) -> None:
        assert (await _batch(client, admin_token, body)).status_code == 422

    async def test_exactly_100_ids_is_accepted_up_to_the_404(
        self, client: httpx.AsyncClient, admin_token: str
    ) -> None:
        ids = [str(uuid.uuid4()) for _ in range(100)]

        resp = await _batch(client, admin_token, {"product_ids": ids, "featured": True})

        assert resp.status_code == 404


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class TestHiddenIsStillForSale:
    async def test_hidden_item_goes_to_cart_and_checkout_lines(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        user_token: str,
        seed: Seeder,
        session_factory: async_sessionmaker[AsyncSession],
        db: AsyncEngine,
    ) -> None:
        pid = await seed.product("Oculto")
        await _batch(client, admin_token, {"product_ids": [str(pid)], "visible": False})
        async with db.connect() as conn:
            vid = (
                await conn.execute(
                    text("SELECT id FROM product_variants WHERE product_id = :p"), {"p": pid}
                )
            ).scalar_one()
        headers = auth_headers(user_token)
        await client.delete(f"{API_V1_PREFIX}/sales/cart/", headers=headers)

        try:
            resp = await client.post(
                f"{API_V1_PREFIX}/sales/cart/items",
                json={"variant_id": str(vid), "quantity": 1},
                headers=headers,
            )

            assert resp.status_code == 201, resp.text
            cart_id = uuid.UUID(resp.json()["data"]["id"])
            async with session_factory() as session:
                cart = await CartRepository(session).get_by_id(cart_id)
                assert isinstance(cart, Cart)
                service = CheckoutService(session, OrderRepository(session), AsyncMock())
                lines, subtotal = service._build_lines(cart)
            assert [line["variant_id"] for line in lines] == [vid]
            assert str(subtotal) == "10.00"
        finally:
            await client.delete(f"{API_V1_PREFIX}/sales/cart/", headers=headers)
