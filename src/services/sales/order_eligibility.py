"""Regras puras de elegibilidade das ações administrativas sobre pedidos.

Fonte única: os services de cancelar/reconciliar/reembolsar as aplicam sob lock e o portal
admin as usa para calcular ``allowed_actions``.
"""

from typing import Optional

from src.models.enums import OrderStatusEnum, ReconciliationStatusEnum, TransactionStatusEnum

DISPATCHED_STATUSES = frozenset(
    {OrderStatusEnum.PROCESSING, OrderStatusEnum.SHIPPED, OrderStatusEnum.DELIVERED}
)


def is_cancelable(order_status: OrderStatusEnum) -> bool:
    """Cancelamento direto: somente pedido aguardando pagamento."""
    return order_status == OrderStatusEnum.PENDING_PAYMENT


def is_dispatched(order_status: OrderStatusEnum) -> bool:
    return order_status in DISPATCHED_STATUSES


def is_payment_approved(transaction_status: Optional[TransactionStatusEnum]) -> bool:
    return transaction_status == TransactionStatusEnum.APPROVED


def refund_needs_reconciliation(order_status: OrderStatusEnum, has_reconciliation: bool) -> bool:
    """Sem reconciliação aberta, só um pedido PAID pode iniciar o estorno."""
    return not has_reconciliation and order_status != OrderStatusEnum.PAID


def can_reconcile(
    transaction_status: Optional[TransactionStatusEnum],
    reconciliation_status: Optional[ReconciliationStatusEnum],
) -> bool:
    return (
        is_payment_approved(transaction_status)
        and reconciliation_status is not None
        and reconciliation_status != ReconciliationStatusEnum.RESOLVED
    )


def can_request_refund(
    order_status: OrderStatusEnum,
    transaction_status: Optional[TransactionStatusEnum],
    has_reconciliation: bool,
    refund_already_requested: bool,
) -> bool:
    return (
        not is_dispatched(order_status)
        and is_payment_approved(transaction_status)
        and not refund_needs_reconciliation(order_status, has_reconciliation)
        and not refund_already_requested
    )
