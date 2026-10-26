import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.endpoints.admin._params import PageParams, page_params
from src.core.db import DbSession
from src.models.enums import OrderStatusEnum
from src.repositories.sales.order_repository import AdminOrderFilters, OrderRepository
from src.schemas.admin.orders import AdminOrderDetail, AdminOrderListItem
from src.schemas.response_schema import BaseResponse, PageMeta
from src.services.admin.order_admin_service import (
    AdminOrderNotFoundError,
    InvalidPeriodError,
    OrderAdminService,
    period_bounds,
)

router = APIRouter(prefix="/orders", tags=["Admin - Orders"])


def get_order_admin_service(session: DbSession) -> OrderAdminService:
    return OrderAdminService(OrderRepository(session))


@router.get("", response_model=BaseResponse[list[AdminOrderListItem]])
async def list_orders(
    status_: list[OrderStatusEnum] = Query(default=[], alias="status"),
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    customer: Optional[str] = Query(None, max_length=100),
    page: PageParams = Depends(page_params),
    service: OrderAdminService = Depends(get_order_admin_service),
):
    try:
        start, end = period_bounds(created_from, created_to)
    except InvalidPeriodError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "created_from"],
                    "msg": "created_from não pode ser posterior a created_to.",
                }
            ],
        )
    filters = AdminOrderFilters(
        statuses=status_, created_start=start, created_end=end, customer=customer
    )
    items, total = await service.list_orders(filters, page.skip, page.limit)
    return BaseResponse(data=items, meta=PageMeta(total=total, skip=page.skip, limit=page.limit))


@router.get("/{order_id}", response_model=BaseResponse[AdminOrderDetail])
async def get_order(
    order_id: uuid.UUID,
    service: OrderAdminService = Depends(get_order_admin_service),
):
    try:
        order = await service.get_order(order_id)
    except AdminOrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(data=order)
