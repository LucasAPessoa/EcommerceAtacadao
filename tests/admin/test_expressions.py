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
from src.models.catalog_presentation import ProductSitePresentation
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


async def test_effective_name_and_customized(db: AsyncEngine, seed: Seeder) -> None:
    plain = await seed.product("Plain")
    renamed = await seed.product("Renamed", presentation={"name": "Nome do site"})
    cats = await seed.product("Cats", presentation={"categories_locked": True})
    hidden_only = await seed.product("Hidden", presentation={"visible": False})
    desc = await seed.product("Desc", presentation={"description": "<p>x</p>"})

    async with AsyncSession(db) as session:
        rows = await session.execute(
            select(Product.id, Product.name, ex.effective_name(), ex.customized())
            .outerjoin(ProductSitePresentation, ProductSitePresentation.product_id == Product.id)
            .where(Product.id.in_([plain, renamed, cats, hidden_only, desc]))
        )
        got = {r[0]: (r[1], r[2], r[3]) for r in rows.all()}

    assert got[plain][1] == got[plain][0] and got[plain][2] is False
    assert got[renamed][1] == "Nome do site" and got[renamed][2] is True
    assert got[cats][2] is True
    assert got[hidden_only][2] is False
    assert got[desc][2] is True


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
