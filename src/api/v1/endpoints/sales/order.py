from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.order_schema import OrderResponseSchema
from src.services.sales.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_order_service(session: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(repository=OrderRepository(session))


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
