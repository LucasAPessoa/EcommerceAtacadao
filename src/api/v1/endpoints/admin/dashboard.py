from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.endpoints.admin._params import PageParams, page_params
from src.core.client_config import get_client_config
from src.core.db import DbSession
from src.repositories.admin.dashboard_repository import DashboardRepository
from src.schemas.admin.dashboard import BlingPendingItem, DashboardSummary
from src.schemas.admin.products import PendingReason
from src.schemas.response_schema import BaseResponse, PageMeta
from src.services.admin.dashboard_service import DashboardService, InvalidDashboardPeriodError

router = APIRouter(tags=["Admin - Dashboard"])


def get_dashboard_service(session: DbSession) -> DashboardService:
    return DashboardService(DashboardRepository(session, get_client_config().low_stock_threshold))


@router.get("/dashboard/summary", response_model=BaseResponse[DashboardSummary])
async def dashboard_summary(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    service: DashboardService = Depends(get_dashboard_service),
):
    try:
        summary = await service.summary(from_, to)
    except InvalidDashboardPeriodError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"type": "value_error", "loc": ["query", exc.field], "msg": exc.message}],
        )
    return BaseResponse(data=summary)


@router.get("/bling/pending", response_model=BaseResponse[list[BlingPendingItem]])
async def bling_pending(
    reason: Optional[PendingReason] = None,
    page: PageParams = Depends(page_params),
    service: DashboardService = Depends(get_dashboard_service),
):
    items, total = await service.list_pending(reason, page.skip, page.limit)
    return BaseResponse(data=items, meta=PageMeta(total=total, skip=page.skip, limit=page.limit))
