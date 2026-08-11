from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.integrations.melhor_envio.client import MelhorEnvioError
from src.models.identity import User
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.order_schema import (
    OrderAddressUpdateSchema,
    OrderCreateSchema,
    OrderItemUpdateSchema,
    OrderResponseSchema,
)
from src.services.operations.shipping_service import ShippingService
from src.services.sales.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_order_service(session: AsyncSession = Depends(get_db)) -> OrderService:
    variant_repository = ProductVariantRepository(session)
    return OrderService(
        repository=OrderRepository(session),
        variant_repository=variant_repository,
        shipping_service=ShippingService(variant_repository=variant_repository),
    )


@router.post("/", response_model=BaseResponse[OrderResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Cria um pedido a partir dos itens enviados pelo cliente."""
    try:
        data = await service.create_order(current_user.id, order_in)
        return BaseResponse(status="success", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MelhorEnvioError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/", response_model=BaseResponse[list[OrderResponseSchema]])
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Lista os pedidos do usuário autenticado (admin vê todos os pedidos)."""
    data = await service.list_orders(current_user, skip=skip, limit=limit)
    return BaseResponse(status="success", data=data)


@router.get("/{order_id}", response_model=BaseResponse[OrderResponseSchema])
async def get_order(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Detalhes de um pedido (dono do pedido ou admin)."""
    data = await service.get_order(order_id, current_user)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(status="success", data=data)


@router.patch("/{order_id}/items/{item_id}", response_model=BaseResponse[OrderResponseSchema])
async def update_order_item(
    order_id: UUID,
    item_id: UUID,
    item_in: OrderItemUpdateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Atualiza a quantidade de um item — só funciona com o pedido pendente."""
    try:
        data = await service.update_item_quantity(current_user.id, order_id, item_id, item_in.quantity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido ou item não encontrado.")
    return BaseResponse(status="success", data=data)


@router.delete("/{order_id}/items/{item_id}", response_model=BaseResponse[OrderResponseSchema])
async def remove_order_item(
    order_id: UUID,
    item_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Remove um item do pedido — só funciona com o pedido pendente."""
    try:
        data = await service.remove_item(current_user.id, order_id, item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido ou item não encontrado.")
    return BaseResponse(status="success", data=data)


@router.patch("/{order_id}/address", response_model=BaseResponse[OrderResponseSchema])
async def update_order_address(
    order_id: UUID,
    address_in: OrderAddressUpdateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Troca o endereço de entrega — só funciona com o pedido pendente."""
    try:
        data = await service.update_address(current_user.id, order_id, address_in.address_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MelhorEnvioError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(status="success", data=data)


@router.post("/{order_id}/cancel", response_model=BaseResponse[OrderResponseSchema])
async def cancel_order(
    order_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: OrderService = Depends(get_order_service),
):
    """Cancela o pedido — permitido em qualquer status anterior ao envio."""
    try:
        data = await service.cancel_order(order_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return BaseResponse(status="success", data=data)
