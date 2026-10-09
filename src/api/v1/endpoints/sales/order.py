from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.integrations.mercado_pago.client import MercadoPagoError
from src.models.identity import User
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.order_schema import (
    OrderReconciliationQueueResponseSchema,
    OrderReconciliationResponseSchema,
    OrderResponseSchema,
)
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService
from src.services.sales.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_order_service(session: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(repository=OrderRepository(session))


def get_mercado_pago_service(session: AsyncSession = Depends(get_db)) -> MercadoPagoCheckoutService:
    return MercadoPagoCheckoutService(checkout_service=None, repository=OrderRepository(session))


@router.get("/", response_model=BaseResponse[list[OrderResponseSchema]])
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Lista os pedidos do usuário autenticado; administradores veem todos."""
    data = await service.list_orders(current_user, skip=skip, limit=limit)
    return BaseResponse(status="success", data=data)


@router.get(
    "/payment-reconciliations/queue",
    response_model=BaseResponse[list[OrderReconciliationQueueResponseSchema]],
)
async def list_payment_reconciliation_queue(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role(["admin"])),
    service: MercadoPagoCheckoutService = Depends(get_mercado_pago_service),
):
    """Fila durável de pagamentos aprovados que requerem ação operacional."""
    reconciliations = await service.repository.list_pending_reconciliations(skip=skip, limit=limit)
    data = []
    for reconciliation in reconciliations:
        refund = await service.repository.get_refund_for_transaction(reconciliation.transaction_id)
        item = OrderReconciliationResponseSchema.model_validate(reconciliation).model_dump()
        item.update(
            refund_status=refund.status if refund else None,
            refund_attempts=refund.attempts if refund else None,
            refund_last_attempt_at=refund.last_attempt_at if refund else None,
            refund_next_retry_at=refund.next_retry_at if refund else None,
            refund_last_error_code=refund.last_error_code if refund else None,
        )
        data.append(OrderReconciliationQueueResponseSchema.model_validate(item))
    return BaseResponse(status="success", data=data)


@router.get("/{order_id}", response_model=BaseResponse[OrderResponseSchema])
async def get_order(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Retorna um pedido do cliente ou qualquer pedido para administradores."""
    data = await service.get_order(order_id, current_user)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(status="success", data=data)


@router.post("/{order_id}/cancel", response_model=BaseResponse[OrderResponseSchema])
async def cancel_order(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Cancela um pedido não pago e libera suas reservas de estoque."""
    try:
        data = await service.cancel_order(order_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(status="success", data=data)


@router.post("/{order_id}/reconcile", response_model=BaseResponse[dict])
async def reconcile_payment(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin"])),
    service: MercadoPagoCheckoutService = Depends(get_mercado_pago_service),
):
    try:
        await service.reconcile_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return BaseResponse(status="success", data={"reconciled": True})


@router.post("/{order_id}/request-refund", response_model=BaseResponse[dict])
async def request_payment_refund(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin"])),
    service: MercadoPagoCheckoutService = Depends(get_mercado_pago_service),
):
    try:
        await service.request_full_refund(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MercadoPagoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BaseResponse(status="success", data={"refund_requested": True})
