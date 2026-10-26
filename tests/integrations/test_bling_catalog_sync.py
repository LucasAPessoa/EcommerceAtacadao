"""Importação do catálogo do Bling (US1/US2): serviço contra Postgres real + Bling simulado.

Usa um banco descartável criado no mesmo servidor do ``DATABASE_URL`` (nunca o banco da API,
cujo seed outros testes usam). Exige as variáveis do ``scripts/run_api_tests.sh``
(BLING_FAKE_URL, BLING_API_BASE_URL, BLING_TOKEN_ENCRYPTION_KEY e DATABASE_URL local).
Falta de ambiente falha o teste.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
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
from src.integrations.bling.catalog import BlingCatalogClient, format_changed_since
from src.integrations.bling.client import BlingClient, RateLimiter
from src.integrations.bling.errors import BlingRateLimitedError
from src.models.base import Base
from src.models.catalog import (
    Category,
    PricingTier,
    Product,
    ProductImage,
    ProductVariant,
)
from src.models.catalog_sync import CatalogSyncRun, CatalogSyncState
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncPhaseEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
    OrderStatusEnum,
    StockReservationStatusEnum,
)
from src.models.identity import Role, User
from src.models.integrations import BlingConnection
from src.models.sales import Order, StockReservation
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
from src.services.catalog.catalog_sync_service import (
    OUTCOME_BUSY,
    OUTCOME_FINISHED,
    CatalogSyncService,
    JobResult,
    SliceResult,
)
from src.services.integrations.bling_connection_service import BlingTokenProvider

Factory = async_sessionmaker[AsyncSession]

# Ids reais do Bling têm 11 dígitos (> 2^31): os helpers somam este deslocamento aos ids
# pequenos usados nos testes (produto, variação, saldo, falha simulada) e o subtraem na leitura.
BIG = 16_724_017_600


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = make_url(_env("DATABASE_URL"))
    assert url.host in {"localhost", "127.0.0.1", "postgres", "db"}, "banco não é efêmero"
    name = f"catalog_sync_{uuid.uuid4().hex[:12]}"
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


def _product(
    bling_id: int,
    name: str = "Arroz 5kg",
    *,
    price: float = 25.9,
    weight: float = 5.0,
    situation: str = "A",
    variations: Optional[list[dict[str, Any]]] = None,
    images: tuple[str, ...] = ("https://img/a.jpg",),
    category: Optional[int] = 1,
    changed: Optional[str] = None,
) -> dict[str, Any]:
    shifted = [{**entry, "id": entry["id"] + BIG} for entry in variations or []]
    return {
        "id": bling_id + BIG,
        "nome": name,
        "codigo": f"P{bling_id}",
        "preco": price,
        "situacao": situation,
        "formato": "V" if variations else "S",
        "pesoBruto": weight,
        "dimensoes": {"largura": 20, "altura": 30, "profundidade": 10},
        "categoria": {"id": category} if category else None,
        "midia": {"imagens": {"externas": [{"link": u} for u in images]}},
        "variacoes": shifted,
        "dataAlteracao": changed,
    }


def _now() -> str:
    return (datetime.utcnow() + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")


def _shift_failure(key: str) -> str:
    head, _, tail = key.rpartition(":")
    return f"{head}:{int(tail) + BIG}" if key.startswith("produtos:detail:") else key


async def _bling(
    fake: httpx.AsyncClient,
    products: list[dict[str, Any]],
    balances: Optional[dict[int, int]] = None,
    failures: Optional[dict[str, int]] = None,
) -> None:
    config = {
        "products": products,
        "categories": [{"id": 1, "descricao": "Mercearia"}],
        "balances": {str(k + BIG): v for k, v in (balances or {}).items()},
        "catalog_failures": {_shift_failure(k): v for k, v in (failures or {}).items()},
    }
    assert (await fake.post("/__control/config", json=config)).status_code == 200


def _service(factory: Factory, session: AsyncSession, **kwargs: Any) -> CatalogSyncService:
    client = BlingClient(
        BlingTokenProvider(factory),
        limiter=RateLimiter(rate=10_000),
        max_retries=0,
        base_url=_env("BLING_API_BASE_URL"),
    )
    return CatalogSyncService(CatalogSyncRepository(session), BlingCatalogClient(client), **kwargs)


async def _slice(factory: Factory, **kwargs: Any) -> SliceResult:
    async with factory() as session:
        return await _service(factory, session, **kwargs).run_slice(CatalogSyncTriggerEnum.MANUAL)


async def _cycle(factory: Factory, **kwargs: Any) -> CatalogSyncRun:
    for _ in range(100):
        result = await _slice(factory, **kwargs)
        if result.outcome == OUTCOME_FINISHED:
            async with factory() as session:
                run = await session.get(CatalogSyncRun, result.run_id)
                assert run is not None
                return run
        assert result.outcome != OUTCOME_BUSY
    pytest.fail("ciclo não terminou em 100 fatias")


async def _products(factory: Factory) -> dict[int, Product]:
    async with factory() as session:
        rows = (await session.execute(select(Product))).scalars().all()
        return {p.bling_id - BIG: p for p in rows if p.bling_id is not None}


async def _variants(factory: Factory) -> dict[int, ProductVariant]:
    async with factory() as session:
        rows = (await session.execute(select(ProductVariant))).scalars().all()
        return {v.bling_id - BIG: v for v in rows if v.bling_id is not None}


# ------------------------------------------------------------------ US1


async def test_first_import_creates_catalog(factory: Factory, fake: httpx.AsyncClient) -> None:
    variations = [
        {"id": 101, "codigo": "V-A", "preco": 10, "variacao": {"nome": "Tipo:A"}},
        {
            "id": 102,
            "codigo": "V-B",
            "preco": 12,
            "variacao": {"nome": "Tipo:B"},
            "midia": {"imagens": {"externas": [{"link": "https://img/b.jpg"}]}},
        },
    ]
    await _bling(
        fake,
        [_product(1, variations=variations), _product(2, "Feijão", price=8)],
        {101: 4, 102: 6, 2: 9},
    )
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.SUCCESS
    assert (run.created, run.failed, run.blocked) == (2, 0, 0)

    products = await _products(factory)
    assert set(products) == {1, 2}
    assert all(p.is_active and p.bling_content_hash for p in products.values())
    variants = await _variants(factory)
    assert set(variants) == {101, 102, 2}
    assert variants[101].base_price == Decimal("10.00")
    assert (variants[101].stock_quantity, variants[102].stock_quantity) == (4, 6)
    async with factory() as session:
        categories = (await session.execute(select(Category))).scalars().all()
        assert [c.name for c in categories] == ["Mercearia"]
        images = (
            await session.execute(
                select(ProductImage.variant_id, ProductImage.image_url, ProductImage.is_main)
            )
        ).all()
        by_variant = {vid: url for vid, url, _ in images}
        assert by_variant[variants[101].id] == "https://img/a.jpg"  # herdada do pai
        assert by_variant[variants[102].id] == "https://img/b.jpg"  # própria
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        assert state.phase == CatalogSyncPhaseEnum.IDLE and state.last_complete_cycle_at


async def test_incomplete_product_is_saved_but_not_for_sale(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, weight=0)], {1: 5})
    run = await _cycle(factory)
    assert (run.created, run.blocked) == (1, 1)
    assert [e["code"] for e in run.errors] == ["incompleto_peso"]
    assert run.errors[0]["bling_id"] == 1 + BIG
    assert (await _products(factory))[1].is_active is False
    assert (await _variants(factory))[1].is_active is False


async def test_price_only_on_creation_and_tiers_untouched(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, price=25.9)], {1: 5})
    await _cycle(factory)
    variant = (await _variants(factory))[1]
    async with factory.begin() as session:
        stored = await session.get(ProductVariant, variant.id)
        assert stored is not None
        stored.base_price = Decimal("99.00")
        session.add(
            PricingTier(product_id=stored.product_id, min_quantity=5, unit_price=Decimal("77.00"))
        )
    await _bling(fake, [_product(1, "Arroz Novo", price=30, changed=_now())], {1: 5})
    run = await _cycle(factory)
    assert run.updated == 1
    assert (await _products(factory))[1].name == "Arroz Novo"
    assert (await _variants(factory))[1].base_price == Decimal("99.00")
    async with factory() as session:
        tiers = (await session.execute(select(PricingTier))).scalars().all()
        assert [(t.min_quantity, t.unit_price) for t in tiers] == [(5, Decimal("77.00"))]


async def test_changed_product_updates_name_images_and_dimensions(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1)], {1: 5})
    await _cycle(factory)
    changed = _product(
        1,
        "Arroz Premium",
        weight=6,
        images=("https://img/n1.jpg", "https://img/n2.jpg"),
        changed=_now(),
    )
    await _bling(fake, [changed], {1: 5})
    await _cycle(factory)
    assert (await _products(factory))[1].name == "Arroz Premium"
    variant = (await _variants(factory))[1]
    assert variant.weight_kg == 6
    async with factory() as session:
        urls = (
            (
                await session.execute(
                    select(ProductImage.image_url)
                    .where(ProductImage.variant_id == variant.id)
                    .order_by(ProductImage.image_url)
                )
            )
            .scalars()
            .all()
        )
        assert urls == ["https://img/n1.jpg", "https://img/n2.jpg"]


async def test_stock_discounts_paid_orders_not_registered_in_bling(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1)], {1: 10})
    await _cycle(factory)
    variant = (await _variants(factory))[1]
    now = datetime.utcnow()
    async with factory.begin() as session:
        role = Role(name="user")
        session.add(role)
        await session.flush()
        user = User(role_id=role.id, email="a@b.c", password_hash="x", full_name="A")
        session.add(user)
        await session.flush()
        for qty, status, registered in [
            (3, OrderStatusEnum.PAID, None),
            (2, OrderStatusEnum.SHIPPED, None),
            (4, OrderStatusEnum.PAID, now),  # já refletido no Bling
            (5, OrderStatusEnum.CANCELED, None),  # não pago
        ]:
            order = Order(
                user_id=user.id,
                shipping_address_snapshot={},
                subtotal_amount=Decimal("1"),
                total_amount=Decimal("1"),
                shipping_provider="x",
                status=status,
                bling_registered_at=registered,
            )
            session.add(order)
            await session.flush()
            session.add(
                StockReservation(
                    order_id=order.id,
                    variant_id=variant.id,
                    quantity=qty,
                    status=StockReservationStatusEnum.CONFIRMED,
                    expires_at=now,
                )
            )
    await _cycle(factory)
    refreshed = (await _variants(factory))[1]
    assert refreshed.bling_stock_balance == 10
    assert refreshed.stock_quantity == 5  # 10 - 3 - 2
    await _bling(fake, [_product(1)], {1: 4})
    await _cycle(factory)
    assert (await _variants(factory))[1].stock_quantity == 0  # nunca negativo


async def test_same_hash_writes_nothing(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _bling(fake, [_product(1), _product(2, "Feijão")], {1: 5, 2: 6})
    await _cycle(factory)
    before_products = await _products(factory)
    before_variants = await _variants(factory)
    second = await _cycle(factory)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)
    # Varredura completa dos detalhes: hash igual, ainda sem escrita.
    async with factory.begin() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.last_full_detail_at = datetime.utcnow() - timedelta(days=2)
    third = await _cycle(factory)
    assert (third.created, third.updated, third.unchanged) == (0, 0, 2)
    after_products = await _products(factory)
    after_variants = await _variants(factory)
    for key, product in before_products.items():
        assert after_products[key].updated_at == product.updated_at
    for key, variant in before_variants.items():
        assert after_variants[key].updated_at == variant.updated_at
        assert after_variants[key].last_bling_sync == variant.last_bling_sync


async def test_product_error_does_not_stop_the_cycle(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(
        fake,
        [_product(1), _product(2, "Feijão"), _product(3, "Milho")],
        {1: 1, 2: 2, 3: 3},
        failures={"produtos:detail:2": 503},
    )
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.PARTIAL
    assert (run.created, run.failed) == (2, 1)
    assert set(await _products(factory)) == {1, 3}
    assert run.errors[0]["bling_id"] == 2 + BIG


async def test_cycle_resumes_from_cursor_without_duplicates(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(
        fake,
        [_product(i, f"Produto {i}") for i in range(1, 26)],
        {i: i for i in range(1, 26)},
    )
    ticks = iter(range(10_000))
    run = await _cycle(factory, budget_seconds=4, clock=lambda: float(next(ticks)))
    assert run.status == CatalogSyncRunStatusEnum.SUCCESS
    assert run.invocations > 1
    assert run.created == 25
    async with factory() as session:
        total = (await session.execute(select(func.count()).select_from(Product))).scalar_one()
        assert total == 25


async def test_busy_when_state_is_locked(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _bling(fake, [_product(1)], {1: 1})
    async with factory() as holder:
        repository = CatalogSyncRepository(holder)
        await repository.ensure_state()  # a linha 1 é criada e confirmada antes da trava
        assert await repository.lock_state() is not None
        assert (await _slice(factory)).outcome == OUTCOME_BUSY
        await holder.rollback()


# ------------------------------------------------------------------ US2


async def _imported(factory: Factory, fake: httpx.AsyncClient, *products: dict[str, Any]) -> None:
    await _bling(fake, list(products), {int(p["id"]): 5 for p in products})
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.SUCCESS


async def test_inactive_in_bling_is_deactivated(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _imported(factory, fake, _product(1))
    await _bling(fake, [_product(1, situation="I", changed=_now())], {1: 5})
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.SUCCESS
    assert (await _products(factory))[1].is_active is False
    # Sem mudança no Bling: o produto inativo não é detalhado de novo a cada ciclo.
    again = await _cycle(factory)
    assert (again.updated, again.failed) == (0, 0)


async def test_missing_product_is_deactivated_not_deleted_and_can_return(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _imported(factory, fake, _product(1), _product(2, "Feijão"))
    await _bling(fake, [_product(1)], {1: 5})
    run = await _cycle(factory)
    assert run.deactivated == 1
    products = await _products(factory)
    assert products[2].is_active is False and products[2].deleted_at is None
    assert products[1].is_active is True

    await _bling(fake, [_product(1), _product(2, "Feijão")], {1: 5, 2: 5})
    await _cycle(factory)
    products = await _products(factory)
    assert products[2].is_active is True
    assert len(products) == 2  # sem duplicar


async def test_removed_variation_is_deactivated_others_stay_for_sale(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    two = [
        {"id": 101, "codigo": "V-A", "preco": 10, "variacao": {"nome": "Tipo:A"}},
        {"id": 102, "codigo": "V-B", "preco": 12, "variacao": {"nome": "Tipo:B"}},
    ]
    await _imported(factory, fake, _product(1, variations=two))
    await _bling(fake, [_product(1, variations=two[:1], changed=_now())], {101: 5})
    await _cycle(factory)
    variants = await _variants(factory)
    assert (variants[101].is_active, variants[102].is_active) == (True, False)
    assert (await _products(factory))[1].is_active is True


async def test_incomplete_read_never_deactivates(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _imported(factory, fake, _product(1), _product(2, "Feijão"))
    async with factory() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        first_cycle_at = state.last_complete_cycle_at
    await _bling(fake, [_product(1)], {1: 5}, failures={"produtos:list:1": 503})
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.PARTIAL
    assert run.deactivated == 0
    assert all(p.is_active for p in (await _products(factory)).values())
    async with factory() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None and state.phase == CatalogSyncPhaseEnum.IDLE
        # Ciclo parcial não avança a base do filtro: o próximo recomeça a varredura.
        assert state.last_complete_cycle_at == first_cycle_at

    await _bling(fake, [_product(1)], {1: 5})
    healthy = await _cycle(factory)
    assert healthy.status == CatalogSyncRunStatusEnum.SUCCESS and healthy.deactivated == 1


# ------------------------------------------------------------------ correções da revisão


async def _set_connection(factory: Factory, status: BlingConnectionStatusEnum) -> None:
    async with factory.begin() as session:
        connection = (await session.execute(select(BlingConnection))).scalar_one()
        connection.status = status


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (BlingConnectionStatusEnum.RECONNECT_REQUIRED, "bling_reconnect_required"),
        (BlingConnectionStatusEnum.NOT_CONNECTED, "bling_not_connected"),
    ],
)
async def test_abort_mid_cycle_fails_run_and_releases_state(
    factory: Factory,
    fake: httpx.AsyncClient,
    status: BlingConnectionStatusEnum,
    reason: str,
) -> None:
    await _imported(factory, fake, _product(1), _product(2, "Feijão"))
    ticks = iter(range(10_000))
    first = await _slice(factory, budget_seconds=2, clock=lambda: float(next(ticks)))
    assert first.outcome == "PROGRESS"  # ciclo em andamento, fase gravada

    await _set_connection(factory, status)
    aborted = await _slice(factory)
    assert aborted.outcome == OUTCOME_FINISHED
    assert aborted.run_status == CatalogSyncRunStatusEnum.FAILED

    async with factory() as session:
        run = await session.get(CatalogSyncRun, aborted.run_id)
        assert run is not None
        assert run.status == CatalogSyncRunStatusEnum.FAILED
        assert run.reason == reason and run.finished_at is not None
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        assert state.phase == CatalogSyncPhaseEnum.IDLE and state.current_run_id is None
    assert all(p.is_active for p in (await _products(factory)).values())

    # Não fica preso: reconectado, o ciclo seguinte roda normalmente.
    await _set_connection(factory, BlingConnectionStatusEnum.CONNECTED)
    assert (await _cycle(factory)).status == CatalogSyncRunStatusEnum.SUCCESS


async def test_zero_price_is_not_for_sale_until_site_price_is_set(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, price=0)], {1: 5})
    run = await _cycle(factory)
    assert (run.created, run.blocked) == (1, 1)
    assert [e["code"] for e in run.errors] == ["incompleto_preco"]
    variant = (await _variants(factory))[1]
    assert variant.is_active is False and variant.base_price == Decimal("0.00")
    product = (await _products(factory))[1]
    assert product.is_active is False and product.bling_content_hash

    async with factory.begin() as session:
        stored = await session.get(ProductVariant, variant.id)
        assert stored is not None
        stored.base_price = Decimal("12.50")
    await _cycle(factory)
    variant = (await _variants(factory))[1]
    assert variant.is_active is True and variant.base_price == Decimal("12.50")
    assert (await _products(factory))[1].is_active is True


async def test_empty_scan_never_deactivates(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _imported(factory, fake, _product(1))
    await _bling(fake, [])
    run = await _cycle(factory)
    assert run.status == CatalogSyncRunStatusEnum.PARTIAL
    assert run.reason == "scan_vazio" and run.deactivated == 0
    assert (await _products(factory))[1].is_active is True


async def test_block_errors_do_not_exhaust_error_list(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    products = [_product(i, f"P{i}", weight=0) for i in range(1, 106)]
    products.append(_product(500, "Falha"))
    await _bling(fake, products, failures={"produtos:detail:500": 503})
    run = await _cycle(factory)
    assert run.blocked == 105
    blocks = [e for e in run.errors if e["code"].startswith("incompleto_")]
    assert len(blocks) == 100
    assert any(e["code"] == "leitura_detalhe" and e["bling_id"] == 500 + BIG for e in run.errors)


async def test_price_blocked_product_is_not_reread_or_rewritten(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, price=0), _product(2, "Feijão")], {1: 5, 2: 5})
    await _cycle(factory)
    before_product = (await _products(factory))[1]
    before_variant = (await _variants(factory))[1]

    def detail_calls(calls: list[dict[str, Any]]) -> int:
        return sum(1 for c in calls if c["path"] == f"/catalogo/produtos:detail:{1 + BIG}")

    calls_before = detail_calls((await fake.get("/__control/calls")).json())
    assert calls_before == 1
    second = await _cycle(factory)
    assert (second.created, second.updated, second.blocked, second.failed) == (0, 0, 0, 0)
    assert second.errors == []
    assert detail_calls((await fake.get("/__control/calls")).json()) == calls_before
    after_product = (await _products(factory))[1]
    after_variant = (await _variants(factory))[1]
    assert after_product.updated_at == before_product.updated_at
    assert after_variant.updated_at == before_variant.updated_at
    assert after_variant.last_bling_sync == before_variant.last_bling_sync
    assert after_variant.is_active is False


async def test_unknown_category_warns_once_and_is_not_reread_or_rewritten(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, category=999), _product(2, "Feijão")], {1: 5, 2: 5})
    first = await _cycle(factory)
    assert (first.created, first.failed, first.blocked) == (2, 0, 0)
    warnings = [e for e in first.errors if e["code"] == "categoria_desconhecida"]
    assert [w["bling_id"] for w in warnings] == [1 + BIG]
    assert "999" in warnings[0]["message"]
    before = (await _products(factory))[1]
    assert before.bling_content_hash is not None

    def detail_calls(calls: list[dict[str, Any]]) -> int:
        return sum(1 for c in calls if c["path"] == f"/catalogo/produtos:detail:{1 + BIG}")

    calls_before = detail_calls((await fake.get("/__control/calls")).json())
    second = await _cycle(factory)
    assert (second.created, second.updated, second.failed) == (0, 0, 0)
    assert detail_calls((await fake.get("/__control/calls")).json()) == calls_before
    assert (await _products(factory))[1].updated_at == before.updated_at


async def test_late_category_links_without_rewriting_product(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1, category=999)], {1: 5})
    await _cycle(factory)
    before = (await _products(factory))[1]
    config = {
        "products": [_product(1, category=999)],
        "categories": [{"id": 1, "descricao": "Mercearia"}, {"id": 999, "descricao": "Nova"}],
        "balances": {str(1 + BIG): 5},
        "catalog_failures": {},
    }
    assert (await fake.post("/__control/config", json=config)).status_code == 200
    async with factory.begin() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.last_full_detail_at = datetime.utcnow() - timedelta(days=2)
    run = await _cycle(factory)
    assert (run.created, run.updated, run.failed) == (0, 1, 0)
    async with factory() as session:
        product = await session.get(Product, before.id, options=[selectinload(Product.categories)])
        assert product is not None
        assert [c.bling_id for c in product.categories] == [999]
        assert product.bling_content_hash == before.bling_content_hash
        assert product.name == before.name
    assert (await _products(factory))[1].updated_at == before.updated_at


# ------------------------------------------------------------------ US3: gatilho (T013/T015)


async def _job(
    factory: Factory,
    trigger: CatalogSyncTriggerEnum = CatalogSyncTriggerEnum.SCHEDULED,
    *,
    force: bool = False,
    **kwargs: Any,
) -> JobResult:
    async with factory() as session:
        return await _service(factory, session, **kwargs).run_job(trigger, None, force=force)


async def _runs(factory: Factory) -> list[CatalogSyncRun]:
    async with factory() as session:
        query = select(CatalogSyncRun).order_by(CatalogSyncRun.started_at)
        return list((await session.execute(query)).scalars().all())


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (BlingConnectionStatusEnum.NOT_CONNECTED, "bling_not_connected"),
        (BlingConnectionStatusEnum.RECONNECT_REQUIRED, "bling_reconnect_required"),
    ],
)
async def test_job_without_connected_bling_is_skipped_and_catalog_intact(
    factory: Factory,
    fake: httpx.AsyncClient,
    status: BlingConnectionStatusEnum,
    reason: str,
) -> None:
    await _imported(factory, fake, _product(1))
    await _set_connection(factory, status)
    await _bling(fake, [])  # se lesse, desativaria; SKIPPED não pode ler nada
    calls_before = len((await fake.get("/__control/calls")).json())

    result = await _job(factory, force=True)
    assert result.status == "SKIPPED" and result.interrupted_by_budget is False
    again = await _job(factory, force=True)
    assert again.run_id == result.run_id  # mesmo motivo seguido: não polui o histórico

    runs = await _runs(factory)
    assert [r.status for r in runs] == [
        CatalogSyncRunStatusEnum.SUCCESS,
        CatalogSyncRunStatusEnum.SKIPPED,
    ]
    assert runs[-1].reason == reason and runs[-1].finished_at is not None
    assert len((await fake.get("/__control/calls")).json()) == calls_before
    assert (await _products(factory))[1].is_active is True


async def test_job_starts_cycle_only_when_interval_elapsed_or_requested(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1)], {1: 5})
    first = await _job(factory)  # nunca rodou: vence
    assert first.status == "SUCCESS" and first.phase == "IDLE"

    idle = await _job(factory)  # terminou agora: ainda não venceu
    assert (idle.status, idle.run_id, idle.interrupted_by_budget) == ("IDLE", None, False)
    assert len(await _runs(factory)) == 1

    async with factory.begin() as session:  # pedido manual pendente
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.requested_at = datetime.utcnow()
    requested = await _job(factory)
    assert requested.status == "SUCCESS" and requested.run_id != first.run_id
    async with factory() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None and state.requested_at is None

    async with factory.begin() as session:  # último fim há mais que o intervalo
        for run in (await session.execute(select(CatalogSyncRun))).scalars():
            run.finished_at = datetime.utcnow() - timedelta(minutes=11)
    assert (await _job(factory)).status == "SUCCESS"
    assert len(await _runs(factory)) == 3


async def test_job_reports_busy_when_state_is_held(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, [_product(1)], {1: 5})
    async with factory() as holder:
        repository = CatalogSyncRepository(holder)
        await repository.ensure_state()
        assert await repository.lock_state() is not None
        busy = await _job(factory, force=True)
        assert (busy.status, busy.run_id, busy.interrupted_by_budget) == ("BUSY", None, False)
        await holder.rollback()
    assert len(await _runs(factory)) == 0


async def test_job_interrupted_by_budget_resumes_and_finishes(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(
        fake, [_product(i, f"Produto {i}") for i in range(1, 16)], {i: i for i in range(1, 16)}
    )
    ticks = iter(range(10_000))
    first = await _job(factory, budget_seconds=3, clock=lambda: float(next(ticks)))
    assert first.status == "RUNNING" and first.interrupted_by_budget is True
    assert first.run_id is not None and first.phase in {"SCAN", "DETAILS", "STOCK", "CATEGORIES"}
    final = first
    for _ in range(50):
        if not final.interrupted_by_budget:
            break
        final = await _job(factory, budget_seconds=3, clock=lambda: float(next(ticks)))
    assert (final.status, final.run_id) == ("SUCCESS", first.run_id)
    runs = await _runs(factory)
    assert len(runs) == 1 and runs[0].created == 15 and runs[0].invocations > 1
    assert len(await _products(factory)) == 15


async def test_bling_429_is_retried_with_backoff(factory: Factory, fake: httpx.AsyncClient) -> None:
    await _bling(fake, [_product(1)], failures={"produtos:list:1": 429})
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    client = BlingClient(
        BlingTokenProvider(factory),
        limiter=RateLimiter(rate=10_000),
        max_retries=2,
        sleep=record,
        base_url=_env("BLING_API_BASE_URL"),
    )
    with pytest.raises(BlingRateLimitedError):
        await BlingCatalogClient(client).list_products_page(1)
    assert len(waits) == 2 and waits[0] >= 1.0 and waits[1] >= 2.0


# ------------------------------------------------------------------ endurecimento (issue #54)


async def test_product_states_with_ids_beyond_int32(factory: Factory) -> None:
    ids = [16_724_017_605 + n for n in range(3)] + [2**31, 2**31 - 1]
    async with factory.begin() as session:
        for n, bling_id in enumerate(ids):
            session.add(
                Product(bling_id=bling_id, name=f"P{n}", status="A", bling_content_hash="h")
            )
    async with factory() as session:
        states = await CatalogSyncRepository(session).product_states([*ids, 16_724_017_999])
    assert set(states) == set(ids)
    assert all(state == ("A", False) for state in states.values())


async def _image_urls(factory: Factory) -> dict[str, str]:
    async with factory() as session:
        rows = (
            await session.execute(
                select(ProductVariant.bling_id, ProductImage.image_url).join(
                    ProductVariant, ProductVariant.id == ProductImage.variant_id
                )
            )
        ).all()
    return {str(bling_id - BIG): url for bling_id, url in rows}


async def test_signed_images_changing_each_read_cause_no_catalog_writes(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    link = "https://orgbling.s3.amazonaws.com/ab/ab"
    await _bling(fake, [_product(1, images=(link,)), _product(2, "Feijão", images=(link + "2",))])
    await fake.post("/__control/config", json={"sign_images": True})
    first = await _cycle(factory)
    assert (first.created, first.failed) == (2, 0)
    before_urls = await _image_urls(factory)
    before_products = await _products(factory)
    before_variants = await _variants(factory)
    async with factory() as session:
        before_image_ids = set((await session.execute(select(ProductImage.id))).scalars())

    # 2º ciclo completo (varredura diária): detalhes relidos, assinaturas novas.
    async with factory.begin() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.last_full_detail_at = datetime.utcnow() - timedelta(days=2)
    second = await _cycle(factory)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)

    after_urls = await _image_urls(factory)
    assert after_urls.keys() == before_urls.keys()
    assert all(after_urls[k] != before_urls[k] for k in before_urls)  # renovadas no lugar
    assert all(after_urls[k].startswith(link) for k in after_urls)
    async with factory() as session:
        assert set((await session.execute(select(ProductImage.id))).scalars()) == before_image_ids
    after_products = await _products(factory)
    after_variants = await _variants(factory)
    for key, product in before_products.items():
        assert after_products[key].updated_at == product.updated_at
    for key, variant in before_variants.items():
        assert after_variants[key].updated_at == variant.updated_at
        assert after_variants[key].last_bling_sync == variant.last_bling_sync


async def test_legacy_products_without_bling_id_are_deactivated_after_full_scan(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    async with factory.begin() as session:
        session.add(Product(name="Seed legado", status="A", is_active=True))
        session.add(Product(name="Seed já inativo", status="A", is_active=False))
    await _imported(factory, fake, _product(1))
    async with factory() as session:
        rows = (await session.execute(select(Product.name, Product.is_active))).all()
        assert dict(rows) == {"Seed legado": False, "Seed já inativo": False, "Arroz 5kg": True}
    runs = await _runs(factory)
    assert runs[0].deactivated == 1


async def test_incomplete_scan_does_not_deactivate_legacy_products(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    async with factory.begin() as session:
        session.add(Product(name="Seed legado", status="A", is_active=True))
    await _bling(fake, [_product(1)], {1: 5}, failures={"produtos:list:1": 503})
    await _cycle(factory)
    async with factory() as session:
        legacy = (
            await session.execute(select(Product).where(Product.name == "Seed legado"))
        ).scalar_one()
        assert legacy.is_active is True


# ---------------------------------------------------- 2ª passada (filtro de alteração)

OLD = "2020-01-01 00:00:00"


def test_changed_since_is_sent_in_sao_paulo_time() -> None:
    assert format_changed_since(datetime(2026, 10, 26, 5, 20)) == "2026-10-26 02:20:00"


def _detail_ids(calls: list[dict[str, Any]]) -> set[str]:
    return {c["path"] for c in calls if c["path"].startswith("/catalogo/produtos:detail:")}


async def _calls_during(
    fake: httpx.AsyncClient, factory: Factory
) -> tuple[CatalogSyncRun, set[str]]:
    before = len((await fake.get("/__control/calls")).json())
    run = await _cycle(factory)
    return run, _detail_ids((await fake.get("/__control/calls")).json()[before:])


def _many(n: int) -> list[dict[str, Any]]:
    return [_product(i, f"P{i}", changed=OLD) for i in range(1, n + 1)]


async def test_ignored_filter_skips_unchanged_details_and_warns_once(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, _many(25))
    await _cycle(factory)
    await fake.post("/__control/config", json={"ignore_changed_filter": True})
    run, details = await _calls_during(fake, factory)
    assert details == set()
    assert [e["code"] for e in run.errors].count("filtro_alteracao_ignorado") == 1
    assert run.unchanged == 25


async def test_respected_filter_details_only_changed(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    products = _many(25)
    await _bling(fake, products)
    await _cycle(factory)
    products[3] = _product(4, "P4 novo", changed=_now())
    await _bling(fake, products)
    run, details = await _calls_during(fake, factory)
    assert details == {f"/catalogo/produtos:detail:{4 + BIG}"}
    assert run.updated == 1
    assert not [e for e in run.errors if e["code"] == "filtro_alteracao_ignorado"]


async def test_daily_full_cycle_still_details_everything(
    factory: Factory, fake: httpx.AsyncClient
) -> None:
    await _bling(fake, _many(25))
    await _cycle(factory)
    await fake.post("/__control/config", json={"ignore_changed_filter": True})
    async with factory.begin() as session:
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.last_full_detail_at = datetime.utcnow() - timedelta(days=2)
    run, details = await _calls_during(fake, factory)
    assert len(details) == 25
    assert not [e for e in run.errors if e["code"] == "filtro_alteracao_ignorado"]
