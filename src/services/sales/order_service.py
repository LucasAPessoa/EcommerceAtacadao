import logging
from datetime import UTC, datetime
from typing import Any, List, Optional
from uuid import UUID

from src.integrations.mercado_pago.client import MercadoPagoClient
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.models.identity import User
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.order_schema import OrderResponseSchema

logger = logging.getLogger(__name__)


def _is_admin(user: User) -> bool:
    return getattr(user.role, "name", None) == "admin"


class OrderService:
    """Consultas e transições posteriores ao checkout."""

    def __init__(
        self, repository: OrderRepository, client: MercadoPagoClient | None = None
    ) -> None:
        self.repository = repository
        self.client = client or MercadoPagoClient()

    async def get_order(self, order_id: UUID, current_user: User) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if order is None:
            return None
        return OrderResponseSchema.model_validate(order)

    @staticmethod
    def assert_payment_approved_for_dispatch(order: Any) -> None:
        """Guarda do despacho (PROCESSING/SHIPPED/DELIVERED): exige pagamento APPROVED.

        Contrato obrigatório de qualquer endpoint de despacho futuro: chamar antes de
        mudar o status. Sem esse fluxo na API, o bloqueio de estorno parcial/chargeback
        é a reconciliação MANUAL_REVIEW mais ``payment_status``.
        """
        transactions = list(getattr(order, "transactions", None) or [])
        if not transactions or any(
            transaction.status != TransactionStatusEnum.APPROVED for transaction in transactions
        ):
            raise ValueError(
                "O pedido não pode ser despachado: o pagamento não está aprovado "
                "(estornado, contestado ou pendente)."
            )

    async def list_orders(
        self, current_user: User, skip: int = 0, limit: int = 100
    ) -> List[OrderResponseSchema]:
        if _is_admin(current_user):
            orders = await self.repository.list_all(skip=skip, limit=limit)
        else:
            orders = await self.repository.list_by_user(current_user.id, skip=skip, limit=limit)
        return [OrderResponseSchema.model_validate(order) for order in orders]

    async def cancel_order(
        self, order_id: UUID, current_user: User
    ) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if order is None:
            return None

        now = datetime.now(UTC).replace(tzinfo=None)
        # Commit 1 (curto): o lock da transação serializa com o webhook, que
        # também a bloqueia primeiro. Nenhuma I/O de rede ocorre com o lock aberto.
        # O estado só é validado depois do lock e da releitura: um webhook que
        # confirmou o pagamento enquanto esperávamos não pode ser sobrescrito.
        session = self.repository.session
        await self.repository.get_transaction_for_order(order.id)
        await session.refresh(order, attribute_names=["status", "transactions"])
        for transaction in order.transactions:
            await session.refresh(transaction)
        if order.status != OrderStatusEnum.PENDING_PAYMENT:
            await session.rollback()
            raise ValueError(
                "Somente pedidos aguardando pagamento podem ser cancelados diretamente. "
                "Pedidos pagos exigem reembolso administrativo "
                "(POST /orders/{id}/request-refund)."
            )
        remote_order_ids: list[str] = []
        remote_transactions: list[Any] = []
        creation_pending = False
        for transaction in order.transactions:
            if transaction.gateway_provider not in {"MERCADO_PAGO", "MERCADO_PAGO_PREPARING"}:
                continue
            if transaction.gateway_provider == "MERCADO_PAGO_PREPARING" and not (
                transaction.gateway_ref_id
            ):
                # O checkout ainda cria a Order remota; ele a cancelará ao reler o pedido.
                creation_pending = True
            if transaction.gateway_ref_id:
                remote_order_ids.append(str(transaction.gateway_ref_id))
                remote_transactions.append(transaction)
            if transaction.status in {
                TransactionStatusEnum.PENDING,
                TransactionStatusEnum.PROCESSING,
            }:
                transaction.status = TransactionStatusEnum.CANCELED
        await self.repository.update_status(order, OrderStatusEnum.CANCELED, current_user.id)
        if creation_pending:
            # Reservas ficam até o TTL, como no cancel remoto falho.
            logger.warning("mercado_pago_cancel_pending_creation order_id=%s", order_id)
        elif not remote_order_ids:
            await self.repository.release_active_reservations(order.id, now)
        await self.repository.session.commit()

        if remote_order_ids:
            # Uma aprovação tardia ainda pode chegar enquanto a Order remota
            # estiver ativa: só libere o estoque depois do cancelamento confirmado.
            confirmed = True
            for provider_order_id in remote_order_ids:
                try:
                    await self.client.cancel_order(provider_order_id)
                except Exception as exc:
                    confirmed = False
                    logger.warning(
                        "mercado_pago_cancel_failed order_id=%s error=%s",
                        order_id,
                        type(exc).__name__,
                    )
            if confirmed:
                confirmed_at = datetime.now(UTC).replace(tzinfo=None)
                for transaction in remote_transactions:
                    transaction.cancel_confirmed_at = confirmed_at
                # Commit 2 (curto).
                await self.repository.release_active_reservations(
                    order.id, datetime.now(UTC).replace(tzinfo=None)
                )
                await self.repository.session.commit()
        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)
