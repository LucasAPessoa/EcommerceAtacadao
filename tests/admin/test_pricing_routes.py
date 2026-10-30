"""Rotas admin de preço por variação e confirmação (spec 008, T013/T014).

API local + Bling simulado (variáveis do ``scripts/run_api_tests.sh``). Produtos criados
aqui têm ids de Bling próprios e são removidos no fim.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import src.models  # noqa: F401
from src.core import crypto
from src.models.catalog import PricingTier, Product, ProductVariant
from src.models.enums import PriceSource, PricingStatus
from tests.conftest import API_V1_PREFIX, auth_headers

ADMIN = f"{API_V1_PREFIX}/admin"
SETTINGS = f"{ADMIN}/store/pricing-settings"
STORE_ID = 206_347_377
PRODUCT_BLING_ID = 16_724_099_001
VARIANT_BLING_ID = 16_724_099_002
LINK_ID = 1_029_099_001


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_env("DATABASE_URL"), poolclass=NullPool)
    yield engine
    await engine.dispose()


async def _cleanup(db: AsyncEngine) -> None:
    async with db.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM pricing_tiers WHERE variant_id IN (SELECT id FROM product_variants "
                "WHERE bling_id = :v)"
            ),
            {"v": VARIANT_BLING_ID},
        )
        await conn.execute(
            text("DELETE FROM product_variants WHERE bling_id = :v"), {"v": VARIANT_BLING_ID}
        )
        await conn.execute(
            text("DELETE FROM products WHERE bling_id = :p"), {"p": PRODUCT_BLING_ID}
        )
        await conn.execute(text("DELETE FROM bling_connection_events"))
        await conn.execute(text("DELETE FROM bling_authorization_attempts"))
        await conn.execute(text("DELETE FROM bling_connections"))


@pytest_asyncio.fixture
async def fake(db: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=_env("BLING_FAKE_URL"), timeout=10.0) as c:
        assert (await c.post("/__control/reset")).status_code == 200
        await _cleanup(db)
        access, version = crypto.encrypt("access-test")
        refresh, _ = crypto.encrypt("refresh-test")
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO bling_connections (id, singleton, status, company_id, "
                    "access_token_enc, refresh_token_enc, key_version, access_expires_at, "
                    "created_at, updated_at) VALUES (gen_random_uuid(), true, "
                    "CAST('CONNECTED' AS blingconnectionstatusenum), 'company-a', :a, :r, :v, "
                    ":exp, now(), now())"
                ),
                {
                    "a": access,
                    "r": refresh,
                    "v": version,
                    "exp": datetime.utcnow() + timedelta(hours=1),
                },
            )
        yield c
    await _cleanup(db)


def _bling_link(price: float = 10.0) -> dict[str, Any]:
    return {
        "id": LINK_ID,
        "codigo": "0",
        "preco": price,
        "precoPromocional": 0,
        "produto": {"id": VARIANT_BLING_ID},
        "loja": {"id": STORE_ID},
        "fornecedorLoja": {"id": 0},
        "marcaLoja": {"id": 0},
        "categoriasProdutos": [],
    }


async def _bling(fake: httpx.AsyncClient, failures: dict[str, int] | None = None) -> None:
    config = {"store_links": [_bling_link()], "catalog_failures": failures or {}}
    assert (await fake.post("/__control/config", json=config)).status_code == 200


async def _seed(db: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    maker = async_sessionmaker(db, expire_on_commit=False)
    async with maker.begin() as session:
        product = Product(
            name="Arroz pricing", bling_id=PRODUCT_BLING_ID, is_active=True, store_listed=True
        )
        session.add(product)
        await session.flush()
        variant = ProductVariant(
            product_id=product.id,
            bling_id=VARIANT_BLING_ID,
            bling_sku="PRC-ROUTE-1",
            variation_name="Pacote 5kg",
            base_price=Decimal("10.00"),
            is_active=True,
            bling_store_link_id=LINK_ID,
            store_price=Decimal("10.00"),
            price_source=PriceSource.VARIANT_LINK,
            pricing_status=PricingStatus.PENDING,
        )
        session.add(variant)
        await session.flush()
        session.add(PricingTier(variant_id=variant.id, min_quantity=1, unit_price=Decimal("10.00")))
        return product.id, variant.id


def _url(product_id: uuid.UUID, variant_id: uuid.UUID) -> str:
    return f"{ADMIN}/products/{product_id}/variants/{variant_id}/pricing"


async def _status(db: AsyncEngine, variant_id: uuid.UUID) -> PricingStatus:
    maker = async_sessionmaker(db, expire_on_commit=False)
    async with maker() as session:
        row = (
            await session.execute(
                select(ProductVariant.pricing_status).where(ProductVariant.id == variant_id)
            )
        ).scalar_one()
        return row


class TestSaveTable:
    async def test_success_changes_line_one_in_bling_and_confirms(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake)
        product_id, variant_id = await _seed(db)
        resp = await client.put(
            _url(product_id, variant_id),
            json={"unit_price": "12.50", "tiers": [{"min_quantity": 10, "unit_price": "11.00"}]},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["id"] == str(variant_id)
        assert data["pricing_status"] == "confirmed" and data["published"] is True
        assert data["price_source"] == "variant_link" and data["store_price"] == "12.50"
        assert [(t["min_quantity"], t["unit_price"]) for t in data["pricing_tiers"]] == [
            (1, "12.50"),
            (10, "11.00"),
        ]
        calls = [c for c in (await fake.get("/__control/calls")).json() if c["method"] == "PUT"]
        assert calls and calls[-1]["body"]["preco"] == 12.5

    async def test_tier_not_below_unit_price_is_422(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake)
        product_id, variant_id = await _seed(db)
        resp = await client.put(
            _url(product_id, variant_id),
            json={"unit_price": "10.00", "tiers": [{"min_quantity": 10, "unit_price": "10.00"}]},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422
        assert "menor que o preço de 1 unidade" in resp.json()["detail"]
        assert await _status(db, variant_id) == PricingStatus.PENDING

    async def test_malformed_body_is_422(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake)
        product_id, variant_id = await _seed(db)
        resp = await client.put(
            _url(product_id, variant_id),
            json={"unit_price": "abc"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422

    async def test_unknown_variant_is_404(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake)
        product_id, _ = await _seed(db)
        resp = await client.put(
            _url(product_id, uuid.uuid4()),
            json={"unit_price": "12.50"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404 and resp.json()["detail"] == "Variação não encontrada."

    async def test_missing_scope_is_409_and_changes_nothing(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake, {f"lojas:put:{LINK_ID}": 403})
        product_id, variant_id = await _seed(db)
        resp = await client.put(
            _url(product_id, variant_id),
            json={"unit_price": "12.50"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 409
        assert "escopo de vínculos de produtos" in resp.json()["detail"]
        assert await _status(db, variant_id) == PricingStatus.PENDING

    async def test_bling_failure_is_502_and_changes_nothing(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        await _bling(fake, {f"lojas:put:{LINK_ID}": 400})
        product_id, variant_id = await _seed(db)
        resp = await client.put(
            _url(product_id, variant_id),
            json={"unit_price": "12.50"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 502
        assert resp.json()["detail"].endswith("Nada foi alterado no site.")
        assert await _status(db, variant_id) == PricingStatus.PENDING

    async def test_non_admin_is_403_and_anonymous_401(
        self, client: httpx.AsyncClient, user_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        product_id, variant_id = await _seed(db)
        body = {"unit_price": "12.50"}
        resp = await client.put(
            _url(product_id, variant_id), json=body, headers=auth_headers(user_token)
        )
        assert resp.status_code == 403
        assert (await client.put(_url(product_id, variant_id), json=body)).status_code == 401
        assert await _status(db, variant_id) == PricingStatus.PENDING


class TestConfirm:
    async def test_confirm_product_returns_detail(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        product_id, variant_id = await _seed(db)
        resp = await client.post(
            f"{ADMIN}/products/{product_id}/confirm-pricing", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == str(product_id)
        assert await _status(db, variant_id) == PricingStatus.CONFIRMED

    async def test_confirm_unknown_product_is_404(
        self, client: httpx.AsyncClient, admin_token: str
    ) -> None:
        resp = await client.post(
            f"{ADMIN}/products/{uuid.uuid4()}/confirm-pricing", headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404

    async def test_confirm_batch_counts_confirmed_and_skipped(
        self, client: httpx.AsyncClient, admin_token: str, fake: httpx.AsyncClient, db: AsyncEngine
    ) -> None:
        product_id, variant_id = await _seed(db)
        ghost = uuid.uuid4()
        resp = await client.post(
            f"{ADMIN}/products/confirm-pricing",
            json={"product_ids": [str(product_id), str(ghost)]},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"confirmed": 1, "skipped": [str(ghost)]}
        assert await _status(db, variant_id) == PricingStatus.CONFIRMED

    async def test_confirm_batch_empty_list_is_422(
        self, client: httpx.AsyncClient, admin_token: str
    ) -> None:
        resp = await client.post(
            f"{ADMIN}/products/confirm-pricing",
            json={"product_ids": []},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 422

    async def test_confirm_requires_admin(self, client: httpx.AsyncClient, user_token: str) -> None:
        headers = auth_headers(user_token)
        one = await client.post(f"{ADMIN}/products/{uuid.uuid4()}/confirm-pricing", headers=headers)
        many = await client.post(
            f"{ADMIN}/products/confirm-pricing",
            json={"product_ids": [str(uuid.uuid4())]},
            headers=headers,
        )
        assert (one.status_code, many.status_code) == (403, 403)


class TestPricingSettings:
    async def test_put_then_get_and_creates_missing_row(
        self, client: httpx.AsyncClient, admin_token: str, db: AsyncEngine
    ) -> None:
        headers = auth_headers(admin_token)
        original = (await client.get(SETTINGS, headers=headers)).json()["data"]
        try:
            async with db.begin() as conn:
                await conn.execute(text("DELETE FROM store_settings"))
            default = await client.get(SETTINGS, headers=headers)
            assert default.status_code == 200
            assert default.json()["data"] == {
                "auto_confirm": True,
                "store_configured": True,
                "store_id": STORE_ID,
            }
            put = await client.put(SETTINGS, json={"auto_confirm": False}, headers=headers)
            assert put.status_code == 200 and put.json()["data"]["auto_confirm"] is False
            got = await client.get(SETTINGS, headers=headers)
            assert got.json()["data"]["auto_confirm"] is False
        finally:
            await client.put(
                SETTINGS, json={"auto_confirm": original["auto_confirm"]}, headers=headers
            )

    async def test_rejects_extra_fields_and_non_admin(
        self, client: httpx.AsyncClient, admin_token: str, user_token: str
    ) -> None:
        extra = await client.put(
            SETTINGS,
            json={"auto_confirm": True, "store_id": 1},
            headers=auth_headers(admin_token),
        )
        assert extra.status_code == 422
        user = auth_headers(user_token)
        assert (await client.get(SETTINGS, headers=user)).status_code == 403
        assert (
            await client.put(SETTINGS, json={"auto_confirm": True}, headers=user)
        ).status_code == 403
