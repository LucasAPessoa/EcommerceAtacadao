from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.integrations.melhor_envio.client import MelhorEnvioError
from src.integrations.mercado_pago.client import MercadoPagoError
from src.models.identity import User
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.sales.checkout_schema import (
    CheckoutConfirmSchema,
    CheckoutPreviewRequestSchema,
    CheckoutPreviewResponseSchema,
)
from src.schemas.sales.mercado_pago_schema import (
    MercadoPagoCheckoutResponseSchema,
    MercadoPagoWebhookSchema,
)
from src.schemas.sales.order_schema import OrderResponseSchema
from src.services.operations.shipping_service import ShippingService
from src.services.sales.checkout_service import CheckoutService
from src.services.sales.mercado_pago_service import (
    MercadoPagoCheckoutService,
    MercadoPagoWebhookError,
)

router = APIRouter(prefix="/checkout", tags=["Checkout"])


def get_checkout_service(session: AsyncSession = Depends(get_db)) -> CheckoutService:
    variant_repository = ProductVariantRepository(session)
    return CheckoutService(
        session=session,
        repository=OrderRepository(session),
        shipping_service=ShippingService(variant_repository=variant_repository),
    )


def get_mercado_pago_checkout_service(
    session: AsyncSession = Depends(get_db),
) -> MercadoPagoCheckoutService:
    repository = OrderRepository(session)
    return MercadoPagoCheckoutService(
        checkout_service=CheckoutService(
            session=session,
            repository=repository,
            shipping_service=ShippingService(variant_repository=ProductVariantRepository(session)),
        ),
        repository=repository,
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


@router.post(
    "/mercado-pago",
    response_model=BaseResponse[MercadoPagoCheckoutResponseSchema],
    status_code=status.HTTP_201_CREATED,
)
async def start_mercado_pago_checkout(
    checkout_in: CheckoutConfirmSchema,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    current_user: User = Depends(require_role(["admin", "user"])),
    service: MercadoPagoCheckoutService = Depends(get_mercado_pago_checkout_service),
):
    """Cria um pedido e devolve apenas a URL hospedada do Checkout Pro."""
    try:
        data = await service.start_checkout(current_user.id, checkout_in, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MercadoPagoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MelhorEnvioError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BaseResponse(status="success", data=data)


@router.post("/mercado-pago/webhook", response_model=BaseResponse[dict])
async def mercado_pago_webhook(
    payload: MercadoPagoWebhookSchema,
    request: Request,
    x_signature: str | None = Header(default=None, alias="x-signature"),
    x_request_id: str | None = Header(default=None, alias="x-request-id"),
    service: MercadoPagoCheckoutService = Depends(get_mercado_pago_checkout_service),
):
    """Recebe notificação de Order autenticada e consulta o recurso no provedor."""
    provider_order_id = request.query_params.get("data.id")
    if (
        payload.type != "order"
        or not provider_order_id
        or payload.data.get("id") != provider_order_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evento inválido."
        )
    try:
        service.verify_webhook_signature(provider_order_id, x_signature, x_request_id)
        await service.process_order_webhook(provider_order_id)
    except MercadoPagoWebhookError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except MercadoPagoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return BaseResponse(status="success", data={"received": True})
