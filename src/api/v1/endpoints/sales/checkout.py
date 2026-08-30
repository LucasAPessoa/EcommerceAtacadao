from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.integrations.melhor_envio.client import MelhorEnvioError
from src.models.identity import User
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.checkout_schema import (
    CheckoutConfirmSchema,
    CheckoutPreviewRequestSchema,
    CheckoutPreviewResponseSchema,
)
from src.schemas.sales.order_schema import OrderResponseSchema
from src.services.operations.shipping_service import ShippingService
from src.services.sales.checkout_service import CheckoutService

router = APIRouter(prefix="/checkout", tags=["Checkout"])


def get_checkout_service(session: AsyncSession = Depends(get_db)) -> CheckoutService:
    variant_repository = ProductVariantRepository(session)
    return CheckoutService(
        session=session,
        repository=OrderRepository(session),
        shipping_service=ShippingService(variant_repository=variant_repository),
    )


@router.post("/preview", response_model=BaseResponse[CheckoutPreviewResponseSchema])
async def preview_checkout(
    checkout_in: CheckoutPreviewRequestSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CheckoutService = Depends(get_checkout_service),
):
    """Revalida o carrinho, aplica preços e retorna opções de frete."""
    try:
        data = await service.preview(current_user.id, checkout_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MelhorEnvioError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BaseResponse(status="success", data=data)


@router.post(
    "/confirm",
    response_model=BaseResponse[OrderResponseSchema],
    status_code=status.HTTP_201_CREATED,
)
async def confirm_checkout(
    checkout_in: CheckoutConfirmSchema,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    current_user: User = Depends(require_role(["admin", "user"])),
    service: CheckoutService = Depends(get_checkout_service),
):
    """Cria atomicamente pedido, pagamento pendente e reservas de estoque."""
    try:
        data = await service.confirm(current_user.id, checkout_in, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MelhorEnvioError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BaseResponse(status="success", data=data)
