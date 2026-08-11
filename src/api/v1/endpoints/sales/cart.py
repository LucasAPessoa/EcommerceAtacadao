from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.cart_repository import CartRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.cart_schema import (
    CartItemCreateSchema,
    CartItemUpdateSchema,
    CartResponseSchema,
)
from src.services.sales.cart_service import CartService

router = APIRouter(prefix="/cart", tags=["Cart"])


def get_cart_service(session: AsyncSession = Depends(get_db)) -> CartService:
    return CartService(
        repository=CartRepository(session),
        variant_repository=ProductVariantRepository(session),
    )


@router.get("/", response_model=BaseResponse[CartResponseSchema])
async def get_cart(
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CartService = Depends(get_cart_service),
):
    """Retorna o carrinho do usuário autenticado (cria um vazio se ainda não existir)."""
    data = await service.get_or_create_cart(current_user.id)
    return BaseResponse(status="success", data=data)


@router.post("/items", response_model=BaseResponse[CartResponseSchema], status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(
    item_in: CartItemCreateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CartService = Depends(get_cart_service),
):
    """Adiciona um item ao carrinho. Se a variação já estiver no carrinho, soma a quantidade."""
    try:
        data = await service.add_item(current_user.id, item_in)
        return BaseResponse(status="success", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/items/{item_id}", response_model=BaseResponse[CartResponseSchema])
async def update_cart_item(
    item_id: UUID,
    item_in: CartItemUpdateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CartService = Depends(get_cart_service),
):
    """Atualiza a quantidade de um item do carrinho."""
    data = await service.update_item_quantity(current_user.id, item_id, item_in)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado no carrinho.")
    return BaseResponse(status="success", data=data)


@router.delete("/items/{item_id}", response_model=BaseResponse[CartResponseSchema])
async def remove_cart_item(
    item_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CartService = Depends(get_cart_service),
):
    """Remove um item do carrinho."""
    data = await service.remove_item(current_user.id, item_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado no carrinho.")
    return BaseResponse(status="success", data=data)


@router.delete("/", response_model=BaseResponse[CartResponseSchema])
async def clear_cart(
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CartService = Depends(get_cart_service),
):
    """Esvazia o carrinho do usuário autenticado (remove todos os itens)."""
    data = await service.clear_cart(current_user.id)
    return BaseResponse(status="success", data=data)
