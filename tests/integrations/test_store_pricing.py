"""Tabela de preços por variação (spec 008): serviço contra Postgres real + Bling simulado.

Banco descartável no mesmo servidor do ``DATABASE_URL``; exige as variáveis do
``scripts/run_api_tests.sh`` (BLING_FAKE_URL, BLING_API_BASE_URL, BLING_TOKEN_ENCRYPTION_KEY).
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

import src.models  # noqa: F401  (registra as tabelas)
from src.core import crypto
from src.integrations.bling.catalog import BlingCatalogClient
from src.integrations.bling.client import BlingClient, RateLimiter
from src.models.base import Base
from src.models.catalog import PricingTier, Product, ProductVariant
from src.models.enums import BlingConnectionStatusEnum, PriceSource, PricingStatus
from src.models.integrations import BlingConnection
from src.repositories.catalog.store_pricing_repository import StorePricingRepository
from src.services.catalog.store_pricing_service import (
    MSG_SCOPE,
    PriceTierInput,
    StorePricingBlingError,
    StorePricingConflictError,
    StorePricingNotFoundError,
    StorePricingService,
    StorePricingValidationError,
)
from src.services.integrations.bling_connection_service import BlingTokenProvider

Factory = async_sessionmaker[AsyncSession]

STORE_ID = 206_347_377
PRODUCT_BLING_ID = 16_724_017_601
VARIANT_BLING_ID = 16_724_017_701
LINK_ID = 1_029_000_001


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = make_url(_env("DATABASE_URL"))
    assert url.host in {"localhost", "127.0.0.1", "postgres", "db"}, "banco não é efêmero"
    name = f"store_pricing_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    eng = create_async_engine(url.set(database=name), poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture
async def factory(engine: AsyncEngine) -> AsyncIterator[Factory]:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with maker.begin() as session:
        access, version = crypto.encrypt("access-test")
        refresh, _ = crypto.encrypt("refresh-test")
        session.add(
            BlingConnection(
                status=BlingConnectionStatusEnum.CONNECTED,
                company_id="company-a",
                access_token_enc=access,
                refresh_token_enc=refresh,
                key_version=version,
                access_expires_at=datetime.utcnow() + timedelta(hours=1),
                refresh_expires_at=datetime.utcnow() + timedelta(days=30),
            )
        )
    yield maker


@pytest_asyncio.fixture
async def fake() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=_env("BLING_FAKE_URL"), timeout=10.0) as c:
        assert (await c.post("/__control/reset")).status_code == 200
        yield c


# ------------------------------------------------------------------ helpers


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


async def _setup_bling(
    fake: httpx.AsyncClient, links: list[dict[str, Any]], failures: Optional[dict] = None
) -> None:
    config = {"store_links": links, "catalog_failures": failures or {}}
    assert (await fake.post("/__control/config", json=config)).status_code == 200


async def _calls(fake: httpx.AsyncClient) -> list[dict[str, Any]]:
    rows = (await fake.get("/__control/calls")).json()
    return [c for c in rows if c["method"] in {"PUT", "POST"} and "body" in c]


async def _seed(
    factory: Factory,
    *,
    own_link: bool = True,
    status: PricingStatus = PricingStatus.PENDING,
    tiers: tuple[tuple[int, str], ...] = ((1, "10.00"),),
    published: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory.begin() as session:
        product = Product(
            name="Arroz",
            bling_id=PRODUCT_BLING_ID,
            is_active=True,
            store_listed=True,
            bling_store_link_id=None if own_link else LINK_ID,
        )
        session.add(product)
        await session.flush()
        variant = ProductVariant(
            product_id=product.id,
            bling_id=VARIANT_BLING_ID,
            bling_sku="ARZ-5",
            variation_name="Pacote 5kg",
            base_price=Decimal("10.00"),
            is_active=published,
            bling_store_link_id=LINK_ID if own_link else None,
            store_price=Decimal("10.00"),
            price_source=PriceSource.VARIANT_LINK if own_link else PriceSource.PARENT_LINK,
            pricing_status=status,
        )
        session.add(variant)
        await session.flush()
        for quantity, price in tiers:
            session.add(
                PricingTier(variant_id=variant.id, min_quantity=quantity, unit_price=Decimal(price))
            )
        return product.id, variant.id


def _service(
    factory: Factory, session: AsyncSession, store_id: Optional[int] = STORE_ID
) -> StorePricingService:
    client = BlingClient(
        BlingTokenProvider(factory),
        limiter=RateLimiter(rate=10_000),
        max_retries=0,
        base_url=_env("BLING_API_BASE_URL"),
    )
    return StorePricingService(
        session,
        StorePricingRepository(session),
        BlingCatalogClient(client),
        store_id=store_id,
    )


async def _save(
    factory: Factory,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    unit_price: str,
    tiers: tuple[tuple[int, str], ...] = (),
    store_id: Optional[int] = STORE_ID,
) -> None:
    async with factory() as session:
        await _service(factory, session, store_id).save_table(
            product_id,
            variant_id,
            Decimal(unit_price),
            [PriceTierInput(q, Decimal(p)) for q, p in tiers],
        )


async def _variant(factory: Factory, variant_id: uuid.UUID) -> ProductVariant:
    async with factory() as session:
        row = (
            await session.execute(
                select(ProductVariant)
                .options(selectinload(ProductVariant.pricing_tiers))
                .where(ProductVariant.id == variant_id)
            )
        ).scalar_one()
        return row


def _table(variant: ProductVariant) -> list[tuple[int, Decimal]]:
    return [(t.min_quantity, t.unit_price) for t in variant.pricing_tiers]


# ------------------------------------------------------------------ confirmar


async def test_confirm_without_change_does_not_touch_bling(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    product_id, variant_id = await _seed(factory)
    async with factory() as session:
        assert await _service(factory, session).confirm(product_id) == 1
    variant = await _variant(factory, variant_id)
    assert variant.pricing_status == PricingStatus.CONFIRMED and variant.pricing_confirmed_at
    assert _table(variant) == [(1, Decimal("10.00"))]
    assert await _calls(fake) == []


async def test_confirm_skips_unpublished_and_is_idempotent(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    product_id, variant_id = await _seed(factory, published=False)
    async with factory() as session:
        assert await _service(factory, session).confirm(product_id) == 0
    assert (await _variant(factory, variant_id)).pricing_status == PricingStatus.PENDING


async def test_confirm_unknown_product_is_not_found(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    async with factory() as session:
        with pytest.raises(StorePricingNotFoundError):
            await _service(factory, session).confirm(uuid.uuid4())


async def test_confirm_many(factory: Factory, fake: httpx.AsyncClient) -> None:
    product_id, variant_id = await _seed(factory)
    missing = uuid.uuid4()
    async with factory() as session:
        result = await _service(factory, session).confirm_many([product_id, missing, product_id])
    assert result.confirmed == 1 and result.skipped == [missing]
    assert (await _variant(factory, variant_id)).pricing_status == PricingStatus.CONFIRMED
    async with factory() as session:
        again = await _service(factory, session).confirm_many([product_id])
    assert again.confirmed == 0 and again.skipped == [product_id]


# ------------------------------------------------------------------ faixas


async def test_valid_tiers_replace_table_without_bling_write(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    product_id, variant_id = await _seed(factory, tiers=((1, "10.00"), (5, "9.00"), (20, "8.00")))
    await _save(factory, product_id, variant_id, "10.00", ((10, "8.50"), (30, "7.00")))
    variant = await _variant(factory, variant_id)
    assert _table(variant) == [
        (1, Decimal("10.00")),
        (10, Decimal("8.50")),
        (30, Decimal("7.00")),
    ]
    assert variant.pricing_status == PricingStatus.CONFIRMED
    assert await _calls(fake) == []


@pytest.mark.parametrize(
    ("tiers", "message"),
    [
        (((1, "9.00"),), "pelo menos 2 unidades"),
        (((10, "9.00"), (10, "8.00")), "Já existe uma faixa a partir de 10 unidades"),
        (((10, "10.00"),), "menor que o preço de 1 unidade (R$ 10,00)"),
        (((10, "12.00"),), "menor que o preço de 1 unidade (R$ 10,00)"),
        (((10, "0"),), "maior que zero"),
    ],
)
async def test_invalid_tiers_change_nothing(
    factory: Factory, fake: httpx.AsyncClient, tiers: tuple[tuple[int, str], ...], message: str
) -> None:
    product_id, variant_id = await _seed(factory, tiers=((1, "10.00"), (5, "9.00")))
    with pytest.raises(StorePricingValidationError, match=re.escape(message)):
        await _save(factory, product_id, variant_id, "10.00", tiers)
    variant = await _variant(factory, variant_id)
    assert _table(variant) == [(1, Decimal("10.00")), (5, Decimal("9.00"))]
    assert variant.pricing_status == PricingStatus.PENDING
    assert await _calls(fake) == []


# ------------------------------------------------------------------ mudança da linha 1


async def test_changed_price_with_own_link_puts_read_body(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _setup_bling(fake, [_bling_link(10.0)])
    product_id, variant_id = await _seed(factory)
    await _save(factory, product_id, variant_id, "12.50", ((10, "11.00"),))

    calls = await _calls(fake)
    assert [c["method"] for c in calls] == ["PUT"]
    assert calls[0]["path"] == f"/produtos/lojas/{LINK_ID}"
    assert calls[0]["body"] == {**_bling_link(10.0), "preco": 12.5}  # só o preço muda
    variant = await _variant(factory, variant_id)
    assert _table(variant) == [(1, Decimal("12.50")), (10, Decimal("11.00"))]
    assert variant.base_price == Decimal("12.50") and variant.store_price == Decimal("12.50")
    assert variant.price_source == PriceSource.VARIANT_LINK
    assert variant.pricing_status == PricingStatus.CONFIRMED and variant.pricing_confirmed_at
    assert variant.bling_store_link_id == LINK_ID


async def test_changed_price_with_inherited_link_creates_own_link(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _setup_bling(fake, [{**_bling_link(10.0), "produto": {"id": PRODUCT_BLING_ID}}])
    product_id, variant_id = await _seed(factory, own_link=False)
    await _save(factory, product_id, variant_id, "12.50")

    calls = await _calls(fake)
    assert [c["method"] for c in calls] == ["POST"]
    assert calls[0]["body"] == {
        "produto": {"id": VARIANT_BLING_ID},
        "loja": {"id": STORE_ID},
        "preco": 12.5,
        "codigo": "0",
        "precoPromocional": 0,
    }
    variant = await _variant(factory, variant_id)
    assert variant.bling_store_link_id == LINK_ID + 1
    assert variant.price_source == PriceSource.VARIANT_LINK
    assert variant.store_price == Decimal("12.50")
    async with factory() as session:
        product = (await session.execute(select(Product))).scalar_one()
        assert product.bling_store_link_id == LINK_ID  # o vínculo do pai segue intacto


async def test_bling_failure_returns_error_and_changes_nothing(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _setup_bling(fake, [_bling_link(10.0)], {f"lojas:put:{LINK_ID}": 503})
    product_id, variant_id = await _seed(factory, tiers=((1, "10.00"), (5, "9.00")))
    with pytest.raises(StorePricingBlingError, match="Nada foi alterado no site"):
        await _save(factory, product_id, variant_id, "12.50", ((10, "11.00"),))
    variant = await _variant(factory, variant_id)
    assert _table(variant) == [(1, Decimal("10.00")), (5, Decimal("9.00"))]
    assert variant.pricing_status == PricingStatus.PENDING
    assert variant.base_price == Decimal("10.00") and variant.store_price == Decimal("10.00")


async def test_missing_scope_is_conflict_and_changes_nothing(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _setup_bling(fake, [_bling_link(10.0)], {f"lojas:put:{LINK_ID}": 403})
    product_id, variant_id = await _seed(factory)
    with pytest.raises(StorePricingConflictError) as error:
        await _save(factory, product_id, variant_id, "12.50")
    assert error.value.message == MSG_SCOPE
    variant = await _variant(factory, variant_id)
    assert _table(variant) == [(1, Decimal("10.00"))]
    assert variant.pricing_status == PricingStatus.PENDING


async def test_missing_store_id_is_conflict(
    factory: Factory, fake: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "src.services.catalog.store_pricing_service.get_client_config",
        lambda: SimpleNamespace(bling_store_id=None),
    )
    product_id, variant_id = await _seed(factory, own_link=False)
    async with factory() as session:
        service = _service(factory, session, store_id=None)
        with pytest.raises(StorePricingConflictError, match="BLING_STORE_ID"):
            await service.save_table(product_id, variant_id, Decimal("12.50"), [])
    assert await _calls(fake) == []
    assert _table(await _variant(factory, variant_id)) == [(1, Decimal("10.00"))]


async def test_variant_of_other_product_is_not_found(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    _, variant_id = await _seed(factory)
    with pytest.raises(StorePricingNotFoundError):
        await _save(factory, uuid.uuid4(), variant_id, "10.00")
