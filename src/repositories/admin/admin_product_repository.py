import uuid
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy import Select, and_, exists, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    product_category_table,
)
from src.models.catalog_presentation import ProductSitePresentation
from src.models.identity import User
from src.repositories._like import escape_like
from src.repositories.admin import _expressions as ex

SORTS = ("name", "price", "stock", "updated_at")


@dataclass
class ProductListFilters:
    q: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    active: Optional[bool] = None
    visible: Optional[bool] = None
    featured: Optional[bool] = None
    low_stock: Optional[bool] = None
    pending: Optional[bool] = None
    pricing_status: Optional[str] = None  # "pending" | "confirmed"
    warning: Optional[str] = None  # "tier_not_below_unit" | "store_price_missing" | "price_not_set"
    listed: Optional[bool] = None
    sort: str = "name"
    order: str = "asc"


@dataclass
class ProductDetailData:
    product: Product
    variants: list[tuple[ProductVariant, Optional[str]]]
    bling_categories: list[Category]
    presentation: Optional[ProductSitePresentation]
    updated_by: Optional[User]


_WARNING_COLUMNS = {
    "tier_not_below_unit": "tier_warning",
    "store_price_missing": "store_price_missing",
    "price_not_set": "price_not_set",
}


def _flag(expr: ColumnElement[bool], wanted: bool) -> ColumnElement[bool]:
    return expr if wanted else ~expr


class AdminProductRepository:
    def __init__(self, session: AsyncSession, low_stock_threshold: int):
        self.session = session
        self.low_stock_threshold = low_stock_threshold

    # ---------------------------------------------------------------- listagem

    def _base(self, agg: Any) -> Select[Any]:
        stmt = select(Product.id).select_from(Product)
        stmt = stmt.outerjoin(
            ProductSitePresentation, ProductSitePresentation.product_id == Product.id
        )
        return ex.with_aggregates(stmt, agg).where(Product.deleted_at.is_(None))

    @staticmethod
    def _visible() -> ColumnElement[bool]:
        return func.coalesce(ProductSitePresentation.visible, true())

    @staticmethod
    def _featured() -> ColumnElement[bool]:
        return func.coalesce(ProductSitePresentation.featured, false())

    @staticmethod
    def _updated_at() -> ColumnElement[Any]:
        return func.greatest(
            Product.updated_at,
            func.coalesce(ProductSitePresentation.updated_at, Product.updated_at),
        )

    @staticmethod
    def _category_exists(category_id: uuid.UUID) -> ColumnElement[bool]:
        return exists().where(
            product_category_table.c.product_id == Product.id,
            product_category_table.c.category_id == category_id,
            Category.id == category_id,
            Category.deleted_at.is_(None),
        )

    def _apply_filters(self, stmt: Select[Any], f: ProductListFilters, agg: Any) -> Select[Any]:
        if f.q:
            pattern = f"%{escape_like(f.q.strip())}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.code.ilike(pattern, escape="\\"),
                    exists().where(
                        ProductVariant.product_id == Product.id,
                        ProductVariant.deleted_at.is_(None),
                        or_(
                            ProductVariant.bling_sku.ilike(pattern, escape="\\"),
                            ProductVariant.gtin.ilike(pattern, escape="\\"),
                        ),
                    ),
                )
            )
        if f.category_id is not None:
            stmt = stmt.where(self._category_exists(f.category_id))
        if f.active is not None:
            stmt = stmt.where(Product.is_active.is_(f.active))
        if f.visible is not None:
            stmt = stmt.where(_flag(self._visible(), f.visible))
        if f.featured is not None:
            stmt = stmt.where(_flag(self._featured(), f.featured))
        if f.low_stock is not None:
            low = and_(Product.is_active.is_(True), ex.stock_of(agg) <= self.low_stock_threshold)
            stmt = stmt.where(_flag(low, f.low_stock))
        if f.pending is not None:
            stmt = stmt.where(_flag(ex.pending_count_of(agg) > 0, f.pending))
        if f.pricing_status is not None:
            stmt = stmt.where(
                _flag(ex.count_of(agg, "pricing_pending") > 0, f.pricing_status == "pending")
            )
        if f.warning is not None:
            stmt = stmt.where(ex.count_of(agg, _WARNING_COLUMNS[f.warning]) > 0)
        if f.listed is not None:
            stmt = stmt.where(
                _flag(and_(Product.store_listed.is_(True), Product.is_active.is_(True)), f.listed)
            )
        return stmt

    def _order_by(self, f: ProductListFilters, agg: Any) -> list[Any]:
        keys: dict[str, Any] = {
            "name": func.lower(Product.name),
            "price": agg.c.min_price,
            "stock": ex.stock_of(agg),
            "updated_at": self._updated_at(),
        }
        key = keys[f.sort]
        primary = key.desc().nulls_last() if f.order == "desc" else key.asc().nulls_last()
        return [primary, Product.id]

    async def list(
        self, f: ProductListFilters, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        agg = ex.variant_aggregates()
        filtered = self._apply_filters(self._base(agg), f, agg)

        total = (
            await self.session.execute(select(func.count()).select_from(filtered.subquery()))
        ).scalar_one()

        stmt = (
            filtered.add_columns(
                Product.code,
                Product.name.label("name"),
                Product.name.label("bling_name"),
                and_(Product.store_listed.is_(True), Product.is_active.is_(True)).label(
                    "store_listed"
                ),
                Product.is_active,
                self._visible().label("visible"),
                self._featured().label("featured"),
                agg.c.min_price,
                agg.c.max_price,
                ex.stock_of(agg).label("stock"),
                (Product.is_active & (ex.stock_of(agg) <= self.low_stock_threshold)).label(
                    "low_stock"
                ),
                ex.pending_count_of(agg).label("pending_count"),
                ex.count_of(agg, "pricing_pending").label("pricing_pending"),
                ex.count_of(agg, "tier_warning").label("tier_warning"),
                ex.count_of(agg, "store_price_missing").label("store_price_missing"),
                ex.count_of(agg, "price_not_set").label("price_not_set"),
                self._updated_at().label("updated_at"),
            )
            .order_by(*self._order_by(f, agg))
            .offset(skip)
            .limit(limit)
        )
        rows = [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]
        images = await self._main_images([r["id"] for r in rows])
        for row in rows:
            row["main_image_url"] = images.get(row["id"])
        return rows, total

    async def _main_images(self, product_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Imagem principal: variação à venda primeiro, ``is_main`` primeiro, ordem estável."""
        if not product_ids:
            return {}
        stmt = (
            select(ProductVariant.product_id, ProductImage.image_url)
            .join(ProductImage, ProductImage.variant_id == ProductVariant.id)
            .where(
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(
                ProductVariant.is_active.desc(),
                ProductImage.is_main.desc(),
                ProductVariant.created_at,
                ProductVariant.id,
                ProductImage.created_at,
                ProductImage.id,
            )
        )
        result: dict[uuid.UUID, str] = {}
        for product_id, url in (await self.session.execute(stmt)).all():
            result.setdefault(product_id, url)
        return result

    # ----------------------------------------------------------------- detalhe

    async def get_detail(self, product_id: uuid.UUID) -> Optional[ProductDetailData]:
        product = (
            await self.session.execute(
                select(Product)
                .where(Product.id == product_id, Product.deleted_at.is_(None))
                .options(selectinload(Product.categories))
            )
        ).scalar_one_or_none()
        if product is None:
            return None

        variant_rows = (
            await self.session.execute(
                select(ProductVariant, ex.variant_pending_reason())
                .join(Product, Product.id == ProductVariant.product_id)
                .where(ProductVariant.product_id == product_id, ProductVariant.deleted_at.is_(None))
                .options(
                    selectinload(ProductVariant.images),
                    selectinload(ProductVariant.pricing_tiers),
                    selectinload(ProductVariant.product),
                )
                .order_by(ProductVariant.created_at, ProductVariant.id)
            )
        ).all()
        presentation = await self.session.get(ProductSitePresentation, product_id)
        updated_by = None
        if presentation is not None and presentation.updated_by_user_id is not None:
            updated_by = await self.session.get(User, presentation.updated_by_user_id)

        return ProductDetailData(
            product=product,
            variants=[(row[0], row[1]) for row in variant_rows],
            bling_categories=sorted(
                (c for c in product.categories if c.deleted_at is None), key=lambda c: c.name
            ),
            presentation=presentation,
            updated_by=updated_by,
        )
