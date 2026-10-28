import hashlib
import hmac
import logging
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.core.client_config import get_client_config
from src.core.config import settings
from src.integrations.mercado_pago.client import MercadoPagoClient, MercadoPagoError
from src.models.enums import (
    OrderStatusEnum,
    PaymentMethodEnum,
    ReconciliationOutcomeEnum,
    ReconciliationReasonEnum,
    ReconciliationStatusEnum,
    RefundStatusEnum,
    TransactionStatusEnum,
)
from src.models.operations import Refund
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.checkout_schema import MercadoPagoCheckoutSchema
from src.schemas.sales.mercado_pago_schema import MercadoPagoCheckoutResponseSchema
from src.services.sales.checkout_service import CheckoutService
from src.services.sales.order_eligibility import (
    is_dispatched,
    is_payment_approved,
    refund_needs_reconciliation,
)

logger = logging.getLogger(__name__)


_KNOWN_PENDING_STATUSES = {"created", "processing", "action_required", "pending", "expired"}
_UNDISPATCHED_PAID = {OrderStatusEnum.PAID, OrderStatusEnum.PAYMENT_RECONCILIATION}
# Transições financeiras posteriores à aprovação (estado atual -> novos estados).
_FINANCIAL_TRANSITIONS = {
    TransactionStatusEnum.APPROVED: {
        TransactionStatusEnum.REFUNDED,
        TransactionStatusEnum.PARTIALLY_REFUNDED,
        TransactionStatusEnum.CHARGEBACK,
    },
    TransactionStatusEnum.PARTIALLY_REFUNDED: {
        TransactionStatusEnum.REFUNDED,
        TransactionStatusEnum.CHARGEBACK,
    },
    TransactionStatusEnum.CHARGEBACK: {TransactionStatusEnum.REFUNDED},
    TransactionStatusEnum.REFUNDED: set(),
}


class MercadoPagoWebhookError(ValueError):
    """Webhook não autenticado ou sem dados suficientes para processamento."""


class MercadoPagoCheckoutService:
    def __init__(
        self,
        checkout_service: CheckoutService | None,
        repository: OrderRepository,
        client: MercadoPagoClient | None = None,
    ) -> None:
        self.checkout_service = checkout_service
        self.repository = repository
        self.client = client or MercadoPagoClient()

    @staticmethod
    def _expiration_time(
        reservation_expires_at: datetime | None, order_created_at: datetime | None
    ) -> str:
        """Duração ISO 8601 derivada só de datas persistidas (corpo idêntico em retries).

        Piso em minutos para a Order remota nunca viver além da reserva; mínimo 1.
        """
        if reservation_expires_at is None or order_created_at is None:
            minutes = settings.STOCK_RESERVATION_MINUTES
        else:
            seconds = (
                reservation_expires_at.replace(tzinfo=None) - order_created_at.replace(tzinfo=None)
            ).total_seconds()
            minutes = math.floor(seconds / 60)
        return f"PT{max(1, minutes)}M"

    @staticmethod
    def _order_payload(
        order: Any,
        payer_email: str,
        reservation_expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Monta uma Order do provedor apenas com o snapshot persistido localmente."""
        return_base_url = get_client_config().front_url.rstrip("/")
        order_id = str(order.id)

        def return_url(payment_status: str) -> str:
            return (
                f"{return_base_url}/pagamento/retorno?order_id={order_id}&status={payment_status}"
            )

        payload: dict[str, Any] = {
            "type": "online",
            "processing_mode": "manual",
            "total_amount": f"{Decimal(order.total_amount):.2f}",
            "external_reference": str(order.id),
            "payer": {"email": payer_email},
            # A Order API exige que o total seja a soma dos itens. Um único
            # item agregado evita que descontos e frete gerem valores negativos
            # em items, mantendo o total imutável do pedido local.
            "items": [
                {
                    "title": f"Pedido {order.order_code}",
                    "quantity": 1,
                    "unit_price": f"{Decimal(order.total_amount):.2f}",
                }
            ],
            "config": {
                "online": {
                    "success_url": return_url("success"),
                    "failure_url": return_url("failure"),
                    "pending_url": return_url("pending"),
                    "auto_return": "approved",
                },
            },
        }
        if settings.MERCADO_PAGO_ORDER_EXPIRATION_ENABLED:
            # O link não pode sobreviver à reserva de estoque.
            payload["expiration_time"] = MercadoPagoCheckoutService._expiration_time(
                reservation_expires_at, getattr(order, "created_at", None)
            )
        return payload

    async def start_checkout(
        self,
        user_id: UUID,
        checkout_in: MercadoPagoCheckoutSchema,
        idempotency_key: UUID,
        payer_email: str,
    ) -> MercadoPagoCheckoutResponseSchema:
        # Não crie pedido/reserva local se o gateway não pode receber o checkout.
        validate_config = getattr(self.client, "validate_config", None)
        if validate_config is None:
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")
        validate_config()
        if self.checkout_service is None:
            raise RuntimeError("Serviço de checkout não configurado.")
        order = await self.checkout_service.confirm(
            user_id,
            checkout_in,
            idempotency_key,
            payment_method=PaymentMethodEnum.MERCADO_PAGO,
            installments=1,
        )
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
        # Pedido já cancelado/expirado ou sem reserva viva: não crie Order remota pagável.
        # A validação vem antes de marcar PREPARING para não deixar a transação presa
        # nesse estado quando o checkout é recusado.
        if (
            order.status != OrderStatusEnum.PENDING_PAYMENT
            or await self.repository.count_live_active_reservations(
                order.id, datetime.now(UTC).replace(tzinfo=None)
            )
            == 0
        ):
            await self.repository.session.rollback()
            raise ValueError("Pedido não está mais disponível para pagamento.")
        if transaction.gateway_provider != "MERCADO_PAGO_PREPARING":
            transaction.gateway_provider = "MERCADO_PAGO_PREPARING"
            transaction.gateway_status_detail = "checkout_creation_pending"
        # Não mantenha locks de carrinho/transação durante a chamada remota,
        # inclusive em uma tentativa recuperada no estado PREPARING.
        await self.repository.session.commit()
        reservation_expires_at = await self.repository.get_earliest_active_reservation_expiry(
            order.id
        )
        provider_order = await self.client.create_order(
            self._order_payload(order, payer_email, reservation_expires_at),
            str(idempotency_key),
        )
        if (
            provider_order.get("external_reference") != str(order.id)
            or Decimal(str(provider_order.get("total_amount"))) != Decimal(order.total_amount)
            or provider_order.get("currency") != order.currency
        ):
            raise MercadoPagoError("Order de pagamento inconsistente.")
        # Releia sob o lock da transação: um cancelamento pode ter sido
        # confirmado enquanto a Order remota era criada.
        session = self.repository.session
        # `order` é o schema devolvido por confirm(), não a entidade ORM: o status
        # atual vem de consulta direta, não de session.refresh.
        await self.repository.get_transaction_for_order(order.id)
        current_status = await self.repository.get_order_status(order.id)
        await session.refresh(transaction)
        if current_status in {OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED}:
            # Persista a ref para a guarda do webhook; a Order remota não pode
            # ficar pagável nem devolvemos a URL.
            transaction.gateway_provider = "MERCADO_PAGO"
            transaction.gateway_ref_id = str(provider_order["id"])
            await session.commit()
            try:
                await self.client.cancel_order(str(provider_order["id"]))
            except Exception as exc:
                logger.warning(
                    "mercado_pago_cancel_failed order_id=%s error=%s",
                    order.id,
                    type(exc).__name__,
                )
            raise ValueError("Pedido cancelado durante a criação do pagamento.")
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
        mercado_pago = get_client_config().mercado_pago
        if not signature or not request_id or mercado_pago is None:
            raise MercadoPagoWebhookError("Webhook não autorizado.")
        values = dict(part.split("=", 1) for part in signature.split(",") if "=" in part)
        timestamp, received = values.get("ts"), values.get("v1")
        if not timestamp or not received:
            raise MercadoPagoWebhookError("Webhook não autorizado.")
        manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
        expected = hmac.new(
            mercado_pago.webhook_secret.get_secret_value().encode(),
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise MercadoPagoWebhookError("Webhook não autorizado.")

    # Fonte única: status remotos que significam dinheiro efetivado.
    @staticmethod
    def _funds_captured(order_status: str, status_detail: str) -> bool:
        return order_status == "processed" and status_detail == "accredited"

    @staticmethod
    def _transaction_status(order_status: str, status_detail: str) -> TransactionStatusEnum:
        # Somente "processed/accredited" é confirmação de fundos pela API
        # Orders. Outros estados seguem pendentes para reconciliação segura.
        if MercadoPagoCheckoutService._funds_captured(order_status, status_detail):
            return TransactionStatusEnum.APPROVED
        if order_status == "processed" and status_detail == "partially_refunded":
            return TransactionStatusEnum.PARTIALLY_REFUNDED
        if order_status == "refunded" or status_detail == "refunded":
            return TransactionStatusEnum.REFUNDED
        if order_status in {"cancelled", "canceled"}:
            return TransactionStatusEnum.CANCELED
        if order_status in {"failed", "rejected"}:
            return TransactionStatusEnum.REJECTED
        if order_status == "charged_back":
            # in_process, settled e reimbursed: todos CHARGEBACK; o detalhe
            # distingue revisão manual de devolução total (ver _apply_financial_event).
            return TransactionStatusEnum.CHARGEBACK
        if order_status not in _KNOWN_PENDING_STATUSES:
            logger.warning(
                "mercado_pago_unknown_status status=%s detail=%s",
                order_status[:40],
                status_detail[:40],
            )
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

        reconciliation = await self.repository.get_reconciliation_for_order(order.id, lock=True)
        status_detail = str(provider_order.get("status_detail") or "")
        transaction_status = self._transaction_status(
            str(provider_order.get("status", "")), status_detail
        )
        # Um evento antigo não pode rebaixar uma aprovação. Só passam as
        # transições financeiras posteriores (estorno, chargeback).
        if transaction.status in _FINANCIAL_TRANSITIONS:
            current = transaction.status
            is_transition = transaction_status in _FINANCIAL_TRANSITIONS[current] or (
                # Chargeback reimbursed após in_process/settled; nunca o inverso.
                current == TransactionStatusEnum.CHARGEBACK
                and transaction_status == TransactionStatusEnum.CHARGEBACK
                and status_detail == "reimbursed"
                and transaction.gateway_status_detail != "reimbursed"
            )
            if is_transition:
                transaction.status = transaction_status
                transaction.gateway_status_detail = status_detail[:100] or None
                transaction.webhook_processed_at = datetime.now(UTC).replace(tzinfo=None)
                await self._apply_financial_event(
                    order, transaction, reconciliation, transaction_status, status_detail
                )
                await self.repository.session.flush()
                return
            if (
                current == TransactionStatusEnum.APPROVED
                and reconciliation is not None
                and reconciliation.status != ReconciliationStatusEnum.RESOLVED
            ):
                await self._reconcile_confirmed_payment(order, transaction, reconciliation)
            return
        if order.status in {
            OrderStatusEnum.CANCELED,
            OrderStatusEnum.EXPIRED,
        } and transaction_status in {
            TransactionStatusEnum.PROCESSING,
            TransactionStatusEnum.PENDING,
        }:
            # Order remota não paga para pedido cancelado: evento terminal, no-op.
            return
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
            if order.status == OrderStatusEnum.PENDING_PAYMENT:
                try:
                    await self.repository.confirm_active_reservations(
                        order.id, datetime.now(UTC).replace(tzinfo=None)
                    )
                    await self.repository.update_status(order, OrderStatusEnum.PAID, None)
                except ValueError:
                    transaction.gateway_status_detail = "requires_reconciliation"
                    await self.repository.update_status(
                        order, OrderStatusEnum.PAYMENT_RECONCILIATION, None
                    )
                    if reconciliation is None:
                        await self.repository.create_reconciliation(
                            order.id, transaction.id, datetime.now(UTC).replace(tzinfo=None)
                        )
            elif order.status != OrderStatusEnum.PAID:
                await self._record_nonfulfillable_approval(order, transaction, reconciliation)
        elif transaction_status in {
            TransactionStatusEnum.REJECTED,
            TransactionStatusEnum.CANCELED,
            TransactionStatusEnum.REFUNDED,  # accredited perdido: estoque nunca baixado
        }:
            if order.status == OrderStatusEnum.PENDING_PAYMENT:
                await self.repository.update_status(order, OrderStatusEnum.CANCELED, None)
                await self.repository.release_active_reservations(
                    order.id, datetime.now(UTC).replace(tzinfo=None)
                )
        await self.repository.session.flush()

    async def _apply_financial_event(
        self,
        order: Any,
        transaction: Any,
        reconciliation: Any,
        new_status: TransactionStatusEnum,
        status_detail: str,
    ) -> None:
        """Efeitos de estorno/chargeback no pedido e no estoque (chamado uma vez por evento)."""
        now = datetime.now(UTC).replace(tzinfo=None)
        fully_refunded = new_status == TransactionStatusEnum.REFUNDED or (
            new_status == TransactionStatusEnum.CHARGEBACK and status_detail == "reimbursed"
        )
        if not fully_refunded:
            if new_status == TransactionStatusEnum.PARTIALLY_REFUNDED:
                await self._open_manual_review(
                    order,
                    transaction,
                    reconciliation,
                    ReconciliationReasonEnum.PAYMENT_PARTIALLY_REFUNDED,
                    "payment_partially_refunded",
                )
            else:
                await self._open_manual_review(
                    order,
                    transaction,
                    reconciliation,
                    ReconciliationReasonEnum.PAYMENT_CHARGEBACK,
                    "payment_chargeback",
                )
            return

        if is_dispatched(order.status):
            # Devolução física: sem mexer em status nem em estoque.
            await self._open_manual_review(
                order,
                transaction,
                reconciliation,
                ReconciliationReasonEnum.PAYMENT_REFUNDED,
                "payment_refunded_after_dispatch",
            )
        else:
            if order.status in _UNDISPATCHED_PAID:
                await self.repository.restore_confirmed_stock(order.id, now)
                await self.repository.release_active_reservations(order.id, now)
                await self.repository.update_status(order, OrderStatusEnum.CANCELED, None)
            if reconciliation is not None:
                reconciliation.status = ReconciliationStatusEnum.RESOLVED
                reconciliation.outcome = ReconciliationOutcomeEnum.REFUNDED
                reconciliation.resolved_at = now
                reconciliation.next_retry_at = None
                reconciliation.last_error_code = None
        refund = await self.repository.get_refund_for_transaction(transaction.id)
        if refund is not None:
            refund.status = RefundStatusEnum.COMPLETED
            refund.completed_at = now
            refund.next_retry_at = None
            refund.last_error_code = None

    async def _open_manual_review(
        self,
        order: Any,
        transaction: Any,
        reconciliation: Any,
        reason: ReconciliationReasonEnum,
        error_code: str,
    ) -> None:
        """Abre (ou reabre) a única reconciliação do pedido para revisão manual.

        O modelo permite um registro por pedido (UNIQUE order_id); uma reconciliação
        já resolvida (ex.: FULFILLMENT_CONFIRMED) é histórico de um evento anterior,
        então é reaberta com o novo motivo em vez de criar um segundo registro.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        if reconciliation is None:
            reconciliation = await self.repository.create_reconciliation(
                order.id, transaction.id, now, reason=reason, error_code=error_code
            )
        reconciliation.reason = reason
        reconciliation.status = ReconciliationStatusEnum.IN_REVIEW
        reconciliation.outcome = ReconciliationOutcomeEnum.MANUAL_REVIEW
        reconciliation.last_error_code = error_code
        reconciliation.next_retry_at = None
        reconciliation.resolved_at = None

    async def _record_nonfulfillable_approval(
        self, order: Any, transaction: Any, reconciliation: Any
    ) -> None:
        """Keep captured funds auditable when local fulfillment is no longer eligible."""
        now = datetime.now(UTC).replace(tzinfo=None)
        if reconciliation is None:
            await self.repository.create_reconciliation(
                order.id,
                transaction.id,
                now,
                reason=ReconciliationReasonEnum.CANCELED_ORDER_APPROVED,
                error_code="canceled_order_approved",
            )
            return
        reconciliation.status = ReconciliationStatusEnum.IN_REVIEW
        reconciliation.outcome = ReconciliationOutcomeEnum.MANUAL_REVIEW
        reconciliation.last_error_code = "canceled_order_approved"
        reconciliation.next_retry_at = None

    async def _reconcile_confirmed_payment(
        self, order: Any, transaction: Any, reconciliation: Any
    ) -> None:
        """Tenta fulfillment local sem chamar o gateway sob locks do banco."""
        now = datetime.now(UTC).replace(tzinfo=None)
        reconciliation.attempts += 1
        reconciliation.last_attempt_at = now
        if order.status != OrderStatusEnum.PAYMENT_RECONCILIATION:
            reconciliation.status = ReconciliationStatusEnum.IN_REVIEW
            reconciliation.outcome = ReconciliationOutcomeEnum.MANUAL_REVIEW
            reconciliation.last_error_code = "order_not_eligible_for_fulfillment"
            reconciliation.next_retry_at = None
            await self.repository.session.flush()
            return
        try:
            await self.repository.confirm_active_reservations(order.id, now)
        except ValueError:
            reconciliation.status = ReconciliationStatusEnum.IN_REVIEW
            reconciliation.outcome = ReconciliationOutcomeEnum.MANUAL_REVIEW
            reconciliation.last_error_code = "stock_commit_failed"
            reconciliation.next_retry_at = None
            await self.repository.session.flush()
            return
        reconciliation.status = ReconciliationStatusEnum.RESOLVED
        reconciliation.outcome = ReconciliationOutcomeEnum.FULFILLMENT_CONFIRMED
        reconciliation.resolved_at = now
        reconciliation.next_retry_at = None
        reconciliation.last_error_code = None
        if order.status != OrderStatusEnum.PAID:
            await self.repository.update_status(order, OrderStatusEnum.PAID, None)
        await self.repository.session.flush()

    async def reconcile_order(self, order_id: UUID) -> None:
        """Entrada administrativa idempotente para a fila de reconciliação."""
        transaction = await self.repository.get_transaction_for_mercado_pago_order(order_id)
        order = await self.repository.get_by_id(order_id)
        if transaction is None or order is None or not is_payment_approved(transaction.status):
            raise ValueError("Pedido não possui pagamento aprovado para reconciliar.")
        reconciliation = await self.repository.get_reconciliation_for_order(order_id, lock=True)
        if reconciliation is None:
            return
        if reconciliation.status == ReconciliationStatusEnum.RESOLVED:
            return
        await self._reconcile_confirmed_payment(order, transaction, reconciliation)

    async def request_full_refund(self, order_id: UUID) -> None:
        """Solicita, mas não declara concluído, o estorno total de uma Order aprovada.

        Elegível: reconciliação aberta (fluxo original) ou pedido PAID com transação
        APPROVED ainda não despachado. A conclusão chega pelo webhook.
        """
        transaction = await self.repository.get_transaction_for_mercado_pago_order(order_id)
        if transaction is None or not transaction.gateway_ref_id:
            raise ValueError("Pedido não possui pagamento elegível para estorno.")
        # Validações de estado só depois do lock da transação e da releitura.
        order = await self.repository.get_by_id(order_id)
        if order is None:
            raise ValueError("Pedido não possui pagamento elegível para estorno.")
        await self.repository.session.refresh(order, attribute_names=["status"])
        await self.repository.session.refresh(transaction)
        if is_dispatched(order.status):
            raise ValueError("Pedido já despachado: o estorno exige o fluxo de devolução.")
        if not is_payment_approved(transaction.status):
            raise ValueError("Somente pagamentos aprovados podem ser estornados.")
        reconciliation = await self.repository.get_reconciliation_for_order(order_id, lock=True)
        existing_reason = getattr(reconciliation, "reason", None)
        refund_reason = (
            str(getattr(existing_reason, "value", existing_reason)).lower()
            if existing_reason
            else "stock_commit_failed"
        )
        if reconciliation is None:
            if refund_needs_reconciliation(order.status, False):
                raise ValueError("Pedido não possui reconciliação elegível para estorno.")
            reconciliation = await self.repository.create_reconciliation(
                order_id,
                transaction.id,
                datetime.now(UTC).replace(tzinfo=None),
                reason=ReconciliationReasonEnum.PAYMENT_REFUNDED,
                error_code="admin_refund_requested",
            )
            reconciliation.next_retry_at = None  # nada a re-tentar localmente
            refund_reason = "payment_refunded"
        refund = await self.repository.get_refund_for_reconciliation(transaction.id)
        if refund is not None and refund.gateway_ref_id:
            return
        refund_key = f"refund-{transaction.gateway_ref_id}"
        if refund is None:
            refund = Refund(
                order_id=order_id,
                transaction_id=transaction.id,
                amount_refunded=transaction.amount,
                reason=refund_reason,
                status=RefundStatusEnum.REQUESTED,
                idempotency_key=refund_key,
                attempts=0,
            )
            self.repository.session.add(refund)
        else:
            refund_key = refund.idempotency_key or refund_key
        reconciliation.outcome = ReconciliationOutcomeEnum.REFUND_REQUESTED
        reconciliation.status = ReconciliationStatusEnum.IN_REVIEW
        reconciliation.resolved_at = None
        await self.repository.session.commit()

        try:
            # Antes de repetir uma solicitação cuja resposta pode ter se perdido,
            # releia a Order no provedor; assim a mesma chave não duplica refund.
            provider_order = await self.client.get_order(transaction.gateway_ref_id)
            refund_id = self._refund_id(provider_order)
            if refund_id is None:
                provider_order = await self.client.create_order_refund(
                    transaction.gateway_ref_id, refund_key
                )
                refund_id = self._refund_id(provider_order)
            if refund_id is None:
                raise MercadoPagoError("Não foi possível solicitar o estorno. Tente novamente.")
        except MercadoPagoError:
            now = datetime.now(UTC).replace(tzinfo=None)
            refund.attempts += 1
            refund.last_attempt_at = now
            refund.next_retry_at = now + timedelta(minutes=5)
            refund.last_error_code = "refund_request_failed"
            await self.repository.session.commit()
            raise

        refund.gateway_ref_id = refund_id
        refund.attempts += 1
        refund.last_attempt_at = datetime.now(UTC).replace(tzinfo=None)
        refund.next_retry_at = None
        refund.last_error_code = None
        await self.repository.session.flush()

    @staticmethod
    def _refund_id(provider_order: dict[str, Any]) -> str | None:
        """Lê somente o identificador de refund, não o id da Order pai."""
        transactions = provider_order.get("transactions")
        if not isinstance(transactions, dict):
            return None
        refunds = transactions.get("refunds")
        if not isinstance(refunds, list) or not refunds:
            return None
        latest = refunds[-1]
        if not isinstance(latest, dict) or not latest.get("id"):
            return None
        return str(latest["id"])[:100]
