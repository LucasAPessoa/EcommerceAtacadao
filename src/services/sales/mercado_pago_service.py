import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.core.config import settings
from src.integrations.mercado_pago.client import MercadoPagoClient, MercadoPagoError
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
from src.schemas.sales.mercado_pago_schema import MercadoPagoCheckoutResponseSchema
from src.services.sales.checkout_service import CheckoutService


class MercadoPagoWebhookError(ValueError):
    """Webhook não autenticado ou sem dados suficientes para processamento."""


class MercadoPagoCheckoutService:
    def __init__(
        self,
        checkout_service: CheckoutService,
        repository: OrderRepository,
        client: MercadoPagoClient | None = None,
    ) -> None:
        self.checkout_service = checkout_service
        self.repository = repository
        self.client = client or MercadoPagoClient()

    @staticmethod
    def _order_payload(order: Any) -> dict[str, Any]:
        """Monta uma Order do provedor apenas com o snapshot persistido localmente."""
        return_base_url = settings.MERCADO_PAGO_FRONTEND_BASE_URL.rstrip("/")
        order_id = str(order.id)

        def return_url(payment_status: str) -> str:
            return (
                f"{return_base_url}/pagamento/retorno?order_id={order_id}&status={payment_status}"
            )

        return {
            "type": "online",
            "processing_mode": "manual",
            "total_amount": f"{Decimal(order.total_amount):.2f}",
            "external_reference": str(order.id),
            # A Order API exige que o total seja a soma dos itens. Um único
            # item agregado evita que descontos e frete gerem valores negativos
            # em items, mantendo o total imutável do pedido local.
            "items": [
                {
                    "title": f"Pedido {order.order_code}",
                    "quantity": 1,
                    "unit_price": f"{Decimal(order.total_amount):.2f}",
                    "total_amount": f"{Decimal(order.total_amount):.2f}",
                    "unit_measure": "unit",
                }
            ],
            "config": {
                "notification_url": settings.MERCADO_PAGO_NOTIFICATION_URL,
                "online": {
                    "success_url": return_url("success"),
                    "failure_url": return_url("failure"),
                    "pending_url": return_url("pending"),
                    "auto_return": "approved",
                },
            },
        }

    async def start_checkout(
        self, user_id: UUID, checkout_in: CheckoutConfirmSchema, idempotency_key: UUID
    ) -> MercadoPagoCheckoutResponseSchema:
        order = await self.checkout_service.confirm(user_id, checkout_in, idempotency_key)
        transaction = await self.repository.get_transaction_for_order(order.id)
        if transaction is None:
            raise MercadoPagoError("Não foi possível iniciar o pagamento. Tente novamente.")
        if transaction.gateway_provider == "MERCADO_PAGO" and transaction.checkout_url:
            return MercadoPagoCheckoutResponseSchema(
                order_id=order.id,
                order_code=order.order_code,
                checkout_url=transaction.checkout_url,
                payment_status=transaction.status,
            )
        if transaction.gateway_provider != "MERCADO_PAGO_PREPARING":
            transaction.gateway_provider = "MERCADO_PAGO_PREPARING"
            # Não mantenha bloqueios de carrinho/estoque enquanto a chamada
            # remota acontece. A mesma chave permite recuperar uma resposta
            # perdida sem criar outra Order no Mercado Pago.
            await self.repository.session.commit()
        provider_order = await self.client.create_order(
            self._order_payload(order), str(idempotency_key)
        )
        if (
            provider_order.get("external_reference") != str(order.id)
            or Decimal(str(provider_order.get("total_amount"))) != Decimal(order.total_amount)
            or provider_order.get("currency") != order.currency
        ):
            raise MercadoPagoError("Order de pagamento inconsistente.")
        transaction.gateway_provider = "MERCADO_PAGO"
        transaction.gateway_ref_id = str(provider_order["id"])
        transaction.checkout_url = str(provider_order["checkout_url"])
        await self.repository.session.flush()
        return MercadoPagoCheckoutResponseSchema(
            order_id=order.id,
            order_code=order.order_code,
            checkout_url=transaction.checkout_url,
            payment_status=transaction.status,
        )

    @staticmethod
    def verify_webhook_signature(
        payment_id: str, signature: str | None, request_id: str | None
    ) -> None:
        if not signature or not request_id or not settings.MERCADO_PAGO_WEBHOOK_SECRET:
            raise MercadoPagoWebhookError("Webhook não autorizado.")
        values = dict(part.split("=", 1) for part in signature.split(",") if "=" in part)
        timestamp, received = values.get("ts"), values.get("v1")
        if not timestamp or not received:
            raise MercadoPagoWebhookError("Webhook não autorizado.")
        manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
        expected = hmac.new(
            settings.MERCADO_PAGO_WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise MercadoPagoWebhookError("Webhook não autorizado.")

    @staticmethod
    def _transaction_status(order_status: str, status_detail: str) -> TransactionStatusEnum:
        # Somente "processed/accredited" é confirmação de fundos pela API
        # Orders. Outros estados seguem pendentes para reconciliação segura.
        if order_status == "processed" and status_detail == "accredited":
            return TransactionStatusEnum.APPROVED
        if order_status == "processed" and status_detail == "partially_refunded":
            return TransactionStatusEnum.PARTIALLY_REFUNDED
        if order_status in {"cancelled", "canceled"}:
            return TransactionStatusEnum.CANCELED
        if order_status in {"failed", "rejected"}:
            return TransactionStatusEnum.REJECTED
        return TransactionStatusEnum.PROCESSING

    async def process_order_webhook(self, provider_order_id: str) -> None:
        provider_order = await self.client.get_order(provider_order_id)
        external_reference = provider_order.get("external_reference")
        try:
            order_id = UUID(str(external_reference))
        except (TypeError, ValueError) as exc:
            raise MercadoPagoWebhookError("Order sem pedido válido.") from exc

        transaction = await self.repository.get_transaction_for_mercado_pago_order(order_id)
        if transaction is None:
            raise MercadoPagoWebhookError("Order sem transação correspondente.")

        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise MercadoPagoWebhookError("Order sem pedido correspondente.")
        try:
            amount_matches = Decimal(str(provider_order.get("total_amount"))) == Decimal(
                transaction.amount
            )
        except (ArithmeticError, ValueError):
            amount_matches = False
        if (
            str(provider_order.get("id")) != provider_order_id
            or transaction.gateway_ref_id != provider_order_id
            or not amount_matches
            or provider_order.get("currency") != order.currency
        ):
            raise MercadoPagoWebhookError("Order não corresponde ao pedido.")

        # Webhooks podem ser repetidos e chegar fora de ordem. Um estado já
        # confirmado localmente é terminal para este fluxo: jamais aceite que
        # um evento anterior libere reserva ou rebaixe a auditoria financeira.
        if (
            transaction.status == TransactionStatusEnum.APPROVED
            or order.status == OrderStatusEnum.PAID
        ):
            return

        status_detail = str(provider_order.get("status_detail") or "")
        transaction_status = self._transaction_status(
            str(provider_order.get("status", "")), status_detail
        )
        payments = provider_order.get("transactions", {}).get("payments", [])
        if isinstance(payments, list) and payments and isinstance(payments[0], dict):
            payment_id = payments[0].get("id")
            if payment_id:
                transaction.gateway_payment_id = str(payment_id)[:100]
        transaction.status = transaction_status
        transaction.gateway_status_detail = status_detail[:100] or None
        transaction.webhook_processed_at = datetime.now(UTC).replace(tzinfo=None)
        if transaction_status == TransactionStatusEnum.APPROVED:
            transaction.paid_at = datetime.now(UTC).replace(tzinfo=None)
            if order and order.status != OrderStatusEnum.PAID:
                await self.repository.update_status(order, OrderStatusEnum.PAID, None)
                try:
                    await self.repository.confirm_active_reservations(
                        order.id, datetime.now(UTC).replace(tzinfo=None)
                    )
                except ValueError:
                    transaction.gateway_status_detail = "requires_manual_reconciliation"
                    await self.repository.update_status(order, OrderStatusEnum.PROCESSING, None)
        elif transaction_status in {TransactionStatusEnum.REJECTED, TransactionStatusEnum.CANCELED}:
            if order.status == OrderStatusEnum.PENDING_PAYMENT:
                await self.repository.update_status(order, OrderStatusEnum.CANCELED, None)
                await self.repository.release_active_reservations(
                    order.id, datetime.now(UTC).replace(tzinfo=None)
                )
        await self.repository.session.flush()
