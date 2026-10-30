from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
from src.models.enums import OrderStatusEnum
from src.repositories.admin.dashboard_repository import DashboardRepository
from src.schemas.admin.dashboard import BlingPendingItem, DashboardSummary
from src.schemas.admin.products import PendingReason
from src.services.admin.order_admin_service import STORE_TZ, period_bounds

_TO_REASON = {
    INCOMPLETE_WEIGHT: PendingReason.INCOMPLETE_WEIGHT,
    INCOMPLETE_DIMENSIONS: PendingReason.INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE: PendingReason.INCOMPLETE_PRICE,
    PendingReason.PRICE_NOT_SET.value: PendingReason.PRICE_NOT_SET,
    PendingReason.STORE_PRICE_MISSING.value: PendingReason.STORE_PRICE_MISSING,
    PendingReason.TIER_NOT_BELOW_UNIT.value: PendingReason.TIER_NOT_BELOW_UNIT,
}
_FROM_REASON = {v: k for k, v in _TO_REASON.items()}
MAX_PERIOD_DAYS = 366
CENT = Decimal("0.01")


class InvalidDashboardPeriodError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def resolve_period(start: Optional[date], end: Optional[date], today: date) -> tuple[date, date]:
    """Padrão: últimos 30 dias até hoje (hoje em America/Sao_Paulo)."""
    end = end or today
    start = start or end - timedelta(days=29)
    if start > end:
        raise InvalidDashboardPeriodError("from", "from não pode ser posterior a to.")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise InvalidDashboardPeriodError(
            "to", f"O período não pode passar de {MAX_PERIOD_DAYS} dias."
        )
    return start, end


class DashboardService:
    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    async def summary(self, start: Optional[date], end: Optional[date]) -> DashboardSummary:
        from datetime import datetime

        today = datetime.now(STORE_TZ).date()
        start, end = resolve_period(start, end, today)
        bounds = period_bounds(start, end)
        assert bounds[0] is not None and bounds[1] is not None
        totals = await self.repository.sales_totals(bounds[0], bounds[1])
        average = (
            (totals.revenue / totals.paid_orders).quantize(CENT, rounding=ROUND_HALF_UP)
            if totals.paid_orders
            else Decimal("0.00")
        )
        return DashboardSummary(
            from_=start,
            to=end,
            timezone=STORE_TZ.key,
            revenue=totals.revenue,
            paid_orders=totals.paid_orders,
            average_ticket=average,
            orders_by_status={s.value: totals.by_status.get(s, 0) for s in OrderStatusEnum},
            low_stock_products=await self.repository.low_stock_products(),
            low_stock_threshold=self.repository.low_stock_threshold,
            bling_pending_products=await self.repository.pending_products(),
            pricing_pending_products=await self.repository.pricing_pending_products(),
            tier_warning_products=await self.repository.tier_warning_products(),
            store_price_missing_products=await self.repository.store_price_missing_products(),
        )

    async def list_pending(
        self, reason: Optional[PendingReason], skip: int, limit: int
    ) -> tuple[list[BlingPendingItem], int]:
        rows, total = await self.repository.list_pending(
            _FROM_REASON[reason] if reason else None, skip, limit
        )
        return [
            BlingPendingItem(
                product_id=r.product_id,
                product_name=r.product_name,
                variant_id=r.variant_id,
                bling_sku=r.bling_sku,
                reason=_TO_REASON[r.reason],
            )
            for r in rows
        ], total
