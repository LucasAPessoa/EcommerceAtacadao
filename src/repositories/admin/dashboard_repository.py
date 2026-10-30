from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import Product, ProductVariant
from src.models.enums import OrderStatusEnum
from src.models.sales import Order
from src.repositories.admin import _expressions as ex

REVENUE_STATUSES = (
    OrderStatusEnum.PAID,
    OrderStatusEnum.PROCESSING,
    OrderStatusEnum.SHIPPED,
    OrderStatusEnum.DELIVERED,
)


@dataclass(frozen=True)
class SalesTotals:
    revenue: Decimal
    paid_orders: int
    by_status: dict[OrderStatusEnum, int]


@dataclass(frozen=True)
class PendingRow:
    product_id: Any
    product_name: str
    variant_id: Any
    bling_sku: Optional[str]
    reason: str


class DashboardRepository:
    def __init__(self, session: AsyncSession, low_stock_threshold: int):
        self.session = session
        self.low_stock_threshold = low_stock_threshold

    async def sales_totals(self, start: datetime, end: datetime) -> SalesTotals:
        """Pedidos com ``created_at`` em [start, end) (UTC naive); somas em SQL."""
        in_period = and_(
            Order.created_at >= start, Order.created_at < end, Order.deleted_at.is_(None)
        )
        rows = (
            await self.session.execute(
                select(Order.status, func.count(), func.coalesce(func.sum(Order.total_amount), 0))
                .where(in_period)
                .group_by(Order.status)
            )
        ).all()
        by_status = {status: int(count) for status, count, _ in rows}
        revenue = sum(
            (Decimal(total) for status, _, total in rows if status in REVENUE_STATUSES), Decimal(0)
        )
        paid = sum(count for status, count in by_status.items() if status in REVENUE_STATUSES)
        return SalesTotals(revenue=revenue, paid_orders=paid, by_status=by_status)

    async def low_stock_products(self) -> int:
        agg = ex.variant_aggregates()
        stmt = (
            select(func.count())
            .select_from(Product)
            .where(
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
                ex.stock_of(agg) <= self.low_stock_threshold,
            )
        )
        return int((await self.session.execute(ex.with_aggregates(stmt, agg))).scalar_one())

    async def pending_products(self) -> int:
        return await self._count_products("pending_count")

    async def _count_products(self, column: str) -> int:
        agg = ex.variant_aggregates()
        stmt = (
            select(func.count())
            .select_from(Product)
            .where(Product.deleted_at.is_(None), ex.count_of(agg, column) > 0)
        )
        return int((await self.session.execute(ex.with_aggregates(stmt, agg))).scalar_one())

    async def pricing_pending_products(self) -> int:
        """Produtos com alguma variação publicada com preço pendente."""
        return await self._count_products("pricing_pending")

    async def tier_warning_products(self) -> int:
        return await self._count_products("tier_warning")

    async def store_price_missing_products(self) -> int:
        return await self._count_products("store_price_missing")

    async def list_pending(
        self, reason: Optional[str], skip: int, limit: int
    ) -> tuple[list[PendingRow], int]:
        reason_expr = ex.variant_pending_reason()
        base = (
            select(
                Product.id,
                Product.name.label("name"),
                ProductVariant.id.label("variant_id"),
                ProductVariant.bling_sku,
                reason_expr.label("reason"),
            )
            .select_from(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(reason_expr.is_not(None))
        )
        if reason is not None:
            base = base.where(reason_expr == reason)
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = (
            await self.session.execute(
                base.order_by(Product.name, ProductVariant.bling_sku, ProductVariant.id)
                .offset(skip)
                .limit(limit)
            )
        ).all()
        return [PendingRow(r[0], r[1], r[2], r[3], str(r[4])) for r in rows], total
