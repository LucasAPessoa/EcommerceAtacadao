"""Fixtures do portal admin: Postgres do ``scripts/run_api_tests.sh`` + semeadura por SQL.

Cada teste usa uma ``tag`` única no nome dos produtos; assim as buscas (``q=tag``) enxergam só
o que o próprio teste semeou, mesmo com o seed global e outros testes no mesmo banco.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, AsyncIterator, Optional

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

NOW = datetime(2030, 1, 1, 12, 0, 0)


@dataclass
class V:
    """Variação a semear. Padrão: à venda, completa, R$ 10,00, estoque 1."""

    sku: Optional[str] = None
    price: Decimal | str = "10.00"
    stock: int = 1
    active: bool = True
    weight: Optional[float] = 1.0
    height: Optional[float] = 1.0
    width: Optional[float] = 1.0
    length: Optional[float] = 1.0
    gtin: Optional[str] = None
    deleted: bool = False
    images: list[tuple[str, bool]] = field(default_factory=list)


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    url = os.environ.get("DATABASE_URL")
    assert url, "DATABASE_URL ausente: rode via scripts/run_api_tests.sh"
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()


class Seeder:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.tag = f"zt{uuid.uuid4().hex[:10]}"
        self.products: list[uuid.UUID] = []
        self.categories: list[uuid.UUID] = []

    async def category(self, name: str, *, active: bool = True, deleted: bool = False) -> uuid.UUID:
        cid = uuid.uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO categories (id, name, is_active, deleted_at, created_at,"
                    " updated_at) VALUES (:id, :n, :a, :d, :t, :t)"
                ),
                {
                    "id": cid,
                    "n": f"{self.tag}-{name}",
                    "a": active,
                    "d": NOW if deleted else None,
                    "t": NOW,
                },
            )
        self.categories.append(cid)
        return cid

    async def product(
        self,
        name: str = "Produto",
        *,
        code: Optional[str] = None,
        active: bool = True,
        deleted: bool = False,
        variants: Optional[list[V]] = None,
        categories: tuple[uuid.UUID, ...] = (),
        updated_at: datetime = NOW,
        presentation: Optional[dict[str, Any]] = None,
        site_categories: tuple[uuid.UUID, ...] = (),
        tiers: tuple[tuple[int, str], ...] = (),
    ) -> uuid.UUID:
        pid = uuid.uuid4()
        code = code or f"{self.tag}-{pid.hex[:8]}"
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO products (id, name, code, is_active, store_listed, deleted_at,"
                    " description, brand, unit, status, created_at, updated_at)"
                    " VALUES (:id, :n, :c, :a, true, :d, 'desc bling', 'Marca', 'UN', 'A', :t,"
                    " :u)"
                ),
                {
                    "id": pid,
                    "n": f"{self.tag} {name}",
                    "c": code,
                    "a": active,
                    "d": NOW if deleted else None,
                    "t": NOW,
                    "u": updated_at,
                },
            )
            self.products.append(pid)
            for n, v in enumerate(variants if variants is not None else [V()]):
                vid = uuid.uuid4()
                await conn.execute(
                    text(
                        "INSERT INTO product_variants (id, product_id, bling_sku, variation_name,"
                        " gtin, base_price, stock_quantity, is_active, weight_kg, height_cm,"
                        " width_cm, length_cm, pricing_status, store_price, price_source,"
                        " pricing_confirmed_at, deleted_at, created_at, updated_at) VALUES"
                        " (:id, :p, :sku, 'v', :gtin, :price, :stock, :a, :w, :h, :wd, :l,"
                        " 'CONFIRMED', :price, 'VARIANT_LINK', :t, :d, :t, :t)"
                    ),
                    {
                        "id": vid,
                        "p": pid,
                        "sku": v.sku or f"{code}-{n}",
                        "gtin": v.gtin,
                        "price": Decimal(v.price),
                        "stock": v.stock,
                        "a": v.active,
                        "w": v.weight,
                        "h": v.height,
                        "wd": v.width,
                        "l": v.length,
                        "d": NOW if v.deleted else None,
                        "t": NOW,
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO pricing_tiers (id, variant_id, min_quantity, unit_price,"
                        " created_at, updated_at) VALUES (:id, :v, 1, :u, :t, :t)"
                    ),
                    {"id": uuid.uuid4(), "v": vid, "u": Decimal(v.price), "t": NOW},
                )
                for k, (url, main) in enumerate(v.images):
                    await conn.execute(
                        text(
                            "INSERT INTO product_images (id, variant_id, image_url, is_main,"
                            " created_at, updated_at) VALUES (:id, :v, :u, :m, :t, :t)"
                        ),
                        {"id": uuid.uuid4(), "v": vid, "u": url, "m": main, "t": NOW},
                    )
            for cid in categories:
                await conn.execute(
                    text("INSERT INTO product_category (product_id, category_id) VALUES (:p, :c)"),
                    {"p": pid, "c": cid},
                )
            for cid in site_categories:
                await conn.execute(
                    text(
                        "INSERT INTO product_site_categories (product_id, category_id)"
                        " VALUES (:p, :c)"
                    ),
                    {"p": pid, "c": cid},
                )
            for qty, price in tiers:
                await conn.execute(
                    text(
                        "INSERT INTO pricing_tiers (id, product_id, min_quantity, unit_price,"
                        " created_at, updated_at) VALUES (:id, :p, :q, :u, :t, :t)"
                    ),
                    {"id": uuid.uuid4(), "p": pid, "q": qty, "u": Decimal(price), "t": NOW},
                )
            if presentation is not None:
                values = {
                    "name": None,
                    "description": None,
                    "complementary_description": None,
                    "categories_locked": False,
                    "visible": True,
                    "featured": False,
                    "updated_by_user_id": None,
                    "updated_at": NOW,
                    **presentation,
                }
                await conn.execute(
                    text(
                        "INSERT INTO product_site_presentation (product_id, name, description,"
                        " complementary_description, categories_locked, visible, featured,"
                        " updated_by_user_id, created_at, updated_at) VALUES (:p, :name,"
                        " :description, :complementary_description, :categories_locked,"
                        " :visible, :featured, :updated_by_user_id, :updated_at, :updated_at)"
                    ),
                    {"p": pid, **values},
                )
        return pid

    async def cleanup(self) -> None:
        async with self.engine.begin() as conn:
            for pid in self.products:
                await conn.execute(
                    text(
                        "DELETE FROM product_images WHERE variant_id IN"
                        " (SELECT id FROM product_variants WHERE product_id = :p)"
                    ),
                    {"p": pid},
                )
                await conn.execute(
                    text(
                        "DELETE FROM pricing_tiers WHERE variant_id IN"
                        " (SELECT id FROM product_variants WHERE product_id = :p)"
                    ),
                    {"p": pid},
                )
                for table in (
                    "product_variants",
                    "pricing_tiers",
                    "product_category",
                    "product_site_categories",
                    "product_site_presentation",
                ):
                    await conn.execute(
                        text(f"DELETE FROM {table} WHERE product_id = :p"), {"p": pid}
                    )
                await conn.execute(text("DELETE FROM products WHERE id = :p"), {"p": pid})
            for cid in self.categories:
                await conn.execute(text("DELETE FROM categories WHERE id = :c"), {"c": cid})


@pytest_asyncio.fixture
async def seed(db: AsyncEngine) -> AsyncIterator[Seeder]:
    seeder = Seeder(db)
    yield seeder
    await seeder.cleanup()
