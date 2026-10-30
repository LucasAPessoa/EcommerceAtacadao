"""T007: expressões SQL do portal admin contra o Postgres de ``scripts/run_api_tests.sh``."""

from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
from src.models.catalog import Product, ProductVariant
from src.repositories.admin import _expressions as ex
from tests.admin.conftest import Seeder, V


async def _reasons(db: AsyncEngine, pid: uuid.UUID) -> dict[str, Optional[str]]:
    async with AsyncSession(db) as session:
        rows = await session.execute(
            select(ProductVariant.bling_sku, ex.variant_pending_reason())
            .join(Product, Product.id == ProductVariant.product_id)
            .where(ProductVariant.product_id == pid)
        )
        return {sku.rsplit("-", 1)[-1]: reason for sku, reason in rows.all()}


async def _single_reason(db: AsyncEngine, seed: Seeder, **fields: Any) -> Optional[str]:
    pid = await seed.product(variants=[V(active=False, **fields)])
    return (await _reasons(db, pid))["0"]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"weight": None}, INCOMPLETE_WEIGHT),
        ({"weight": 0}, INCOMPLETE_WEIGHT),
        ({"weight": -1}, INCOMPLETE_WEIGHT),
        ({"width": None}, INCOMPLETE_DIMENSIONS),
        ({"height": 0}, INCOMPLETE_DIMENSIONS),
        ({"length": -2}, INCOMPLETE_DIMENSIONS),
        ({"price": "0.00"}, INCOMPLETE_PRICE),
        ({}, None),
    ],
)
async def test_pending_reason_per_cause(
    db: AsyncEngine, seed: Seeder, fields: dict[str, Any], expected: Optional[str]
) -> None:
    assert await _single_reason(db, seed, **fields) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"weight": None, "width": None, "price": "0.00"}, INCOMPLETE_WEIGHT),
        ({"width": None, "price": "0.00"}, INCOMPLETE_DIMENSIONS),
        ({"weight": 0, "price": "0.00"}, INCOMPLETE_WEIGHT),
    ],
)
async def test_pending_reason_order(
    db: AsyncEngine, seed: Seeder, fields: dict[str, Any], expected: str
) -> None:
    assert await _single_reason(db, seed, **fields) == expected


async def test_pending_reason_only_for_inactive_variant_of_live_product(
    db: AsyncEngine, seed: Seeder
) -> None:
    broken: dict[str, Any] = {"weight": None}
    live = await seed.product(
        variants=[
            V(active=True, **broken),
            V(active=False, **broken),
            V(active=False, deleted=True),
        ]
    )
    deleted = await seed.product(deleted=True, variants=[V(active=False, **broken)])

    assert await _reasons(db, live) == {"0": None, "1": INCOMPLETE_WEIGHT, "2": None}
    assert await _reasons(db, deleted) == {"0": None}


async def test_published_and_price_warnings(db: AsyncEngine, seed: Seeder) -> None:
    tag = seed.tag
    listed = await seed.product(
        variants=[
            V(sku=f"{tag}-ok"),
            V(sku=f"{tag}-pending", status="PENDING"),
            V(sku=f"{tag}-inactive", active=False),
            V(sku=f"{tag}-noline", line_one=False),
            V(sku=f"{tag}-tier", tiers=((5, "10.00"), (9, "7.00"))),
            V(sku=f"{tag}-general", source="GENERAL"),
            V(sku=f"{tag}-zero", price="0.00", source="GENERAL", line_one=False, active=False),
        ]
    )
    unlisted = await seed.product(listed=False, variants=[V(sku=f"{tag}-out", source="GENERAL")])

    async with AsyncSession(db) as session:
        rows = await session.execute(
            select(
                ProductVariant.bling_sku,
                ex.published(),
                ex.pricing_pending(),
                ex.tier_not_below_unit(),
                ex.store_price_missing(),
                ex.price_not_set(),
            )
            .join(Product, Product.id == ProductVariant.product_id)
            .where(Product.id.in_([listed, unlisted]))
        )
        got = {r[0].removeprefix(f"{tag}-"): tuple(r[1:]) for r in rows.all()}

    # (publicada, pendente, faixa>=1un, preço da loja ausente, preço não definido)
    assert got["ok"] == (True, False, False, False, False)
    assert got["pending"] == (True, True, False, False, False)
    assert got["inactive"] == (False, False, False, False, False)
    assert got["noline"] == (False, False, False, False, False)
    assert got["tier"] == (True, False, True, False, False)
    assert got["general"] == (True, False, False, True, False)
    assert got["zero"] == (False, False, False, False, True)
    assert got["out"] == (False, False, False, False, False)  # produto fora da loja


async def test_variant_aggregates(db: AsyncEngine, seed: Seeder) -> None:
    full = await seed.product(
        variants=[
            V(price="12.50", stock=3),
            V(price="30.00", stock=4),
            V(price="1.00", stock=100, active=False, weight=None),  # fora de venda e pendente
            V(price="2.00", stock=100, deleted=True),  # excluída
        ]
    )
    empty = await seed.product(variants=[])
    agg = ex.variant_aggregates()

    async with AsyncSession(db) as session:
        stmt = ex.with_aggregates(select(Product.id).select_from(Product), agg).add_columns(
            ex.stock_of(agg), agg.c.min_price, agg.c.max_price, ex.pending_count_of(agg)
        )
        rows = {
            r[0]: r[1:]
            for r in (await session.execute(stmt.where(Product.id.in_([full, empty])))).all()
        }

    assert rows[full][0] == 7
    assert str(rows[full][1]) == "12.50" and str(rows[full][2]) == "30.00"
    assert rows[full][3] == 1
    assert rows[empty] == (0, None, None, 0)


async def test_price_warnings_ignore_deleted_variant_and_product(
    db: AsyncEngine, seed: Seeder
) -> None:
    tag = seed.tag
    broken: dict[str, Any] = {"source": "GENERAL", "tiers": ((5, "10.00"),)}
    live = await seed.product(
        variants=[
            V(sku=f"{tag}-live", **broken),
            V(sku=f"{tag}-deleted", deleted=True, **broken),
        ]
    )
    dead = await seed.product(deleted=True, variants=[V(sku=f"{tag}-dead", **broken)])

    async with AsyncSession(db) as session:
        rows = await session.execute(
            select(
                ProductVariant.bling_sku,
                ex.tier_not_below_unit(),
                ex.store_price_missing(),
                ex.price_not_set(),
                ex.pricing_pending(),
            )
            .join(Product, Product.id == ProductVariant.product_id)
            .where(Product.id.in_([live, dead]))
        )
        got = {r[0].removeprefix(f"{tag}-"): tuple(r[1:]) for r in rows.all()}

    assert got["live"] == (True, True, False, False)
    assert got["deleted"] == (False, False, False, False)
    assert got["dead"] == (False, False, False, False)


async def test_pending_reason_emits_price_warnings(db: AsyncEngine, seed: Seeder) -> None:
    tag = seed.tag
    pid = await seed.product(
        variants=[
            V(sku=f"{tag}-ok"),
            V(sku=f"{tag}-notset", price="0.00", source="GENERAL", line_one=False, active=False),
            V(sku=f"{tag}-unset", price="0.00", source="GENERAL", line_one=False),
            V(sku=f"{tag}-missing", source="GENERAL"),
            V(sku=f"{tag}-tier", tiers=((5, "10.00"),)),
            V(sku=f"{tag}-tierdel", tiers=((5, "10.00"),), deleted=True),
            V(sku=f"{tag}-weight", active=False, weight=None, source="GENERAL"),
        ]
    )
    unlisted = await seed.product(listed=False, variants=[V(sku=f"{tag}-out", source="GENERAL")])
    dead = await seed.product(deleted=True, variants=[V(sku=f"{tag}-dead", source="GENERAL")])

    got: dict[str, Optional[str]] = {}
    for p in (pid, unlisted, dead):
        got |= {f"{p}/{k}": v for k, v in (await _reasons(db, p)).items()}

    by_sku = {k.split("/", 1)[1]: v for k, v in got.items()}
    assert by_sku == {
        "ok": None,
        "notset": INCOMPLETE_PRICE,  # a incompletude da sync vence o aviso
        "unset": "PRICE_NOT_SET",
        "missing": "STORE_PRICE_MISSING",
        "tier": "TIER_NOT_BELOW_UNIT",
        "tierdel": None,
        "weight": INCOMPLETE_WEIGHT,
        "out": None,
        "dead": None,
    }
