"""Schemas do portal admin: dashboard e pendências do Bling (contracts/http-api.md)."""

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.admin.products import Money, PendingReason


class DashboardSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date
    timezone: str
    revenue: Money
    paid_orders: int
    average_ticket: Money
    orders_by_status: dict[str, int]
    low_stock_products: int
    low_stock_threshold: int
    bling_pending_products: int


class BlingPendingItem(BaseModel):
    product_id: UUID
    product_name: str
    variant_id: UUID
    bling_sku: Optional[str] = None
    reason: PendingReason
