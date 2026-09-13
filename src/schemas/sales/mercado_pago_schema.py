from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl

from src.models.enums import TransactionStatusEnum


class MercadoPagoCheckoutResponseSchema(BaseModel):
    order_id: UUID
    order_code: str
    checkout_url: HttpUrl
    payment_status: TransactionStatusEnum


class MercadoPagoWebhookSchema(BaseModel):
    type: Optional[str] = None
    action: Optional[str] = None
    # A notificação de Order inclui objetos em ``data`` (items e transactions).
    # O endpoint confia somente em ``data.id`` após validar a assinatura e
    # consulta a Order no provedor antes de alterar o pedido local.
    data: dict[str, Any]
