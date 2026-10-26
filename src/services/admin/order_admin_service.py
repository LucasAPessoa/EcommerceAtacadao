from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from src.models.enums import TransactionStatusEnum
from src.repositories.sales.order_repository import AdminOrderFilters, OrderRepository
from src.schemas.admin.orders import (
    AdminOrderCustomer,
    AdminOrderDetail,
    AdminOrderItem,
    AdminOrderListItem,
    AdminOrderReconciliation,
    AdminOrderStatusChange,
    AdminOrderTransaction,
    OrderAction,
)
from src.services.sales.order_eligibility import (
    can_reconcile,
    can_request_refund,
    is_cancelable,
)

STORE_TZ = ZoneInfo("America/Sao_Paulo")
MERCADO_PAGO = "MERCADO_PAGO"


class AdminOrderNotFoundError(Exception):
    pass


class InvalidPeriodError(Exception):
    pass


def _to_utc_naive(local_midnight: datetime) -> datetime:
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def period_bounds(
    created_from: Optional[date], created_to: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Datas inclusivas em America/Sao_Paulo -> [início, fim) em UTC naive (created_at)."""
    if created_from and created_to and created_from > created_to:
        raise InvalidPeriodError()
    start = (
        _to_utc_naive(datetime.combine(created_from, time.min, tzinfo=STORE_TZ))
        if created_from
        else None
    )
    end = (
        _to_utc_naive(datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=STORE_TZ))
        if created_to
        else None
    )
    return start, end


class OrderAdminService:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    async def list_orders(
        self, filters: AdminOrderFilters, skip: int, limit: int
    ) -> tuple[list[AdminOrderListItem], int]:
        rows, total = await self.repository.list_admin(filters, skip, limit)
        items = [
            AdminOrderListItem(
                id=order.id,
                order_code=order.order_code,
                status=order.status,
                created_at=order.created_at,
                total_amount=order.total_amount,
                items_count=count,
                customer=AdminOrderCustomer.model_validate(user),
            )
            for order, user, count in rows
        ]
        return items, total

    async def get_order(self, order_id: UUID) -> AdminOrderDetail:
        data = await self.repository.get_admin_detail(order_id)
        if data is None:
            raise AdminOrderNotFoundError()
        order = data.order
        mp = next((t for t in order.transactions if t.gateway_provider == MERCADO_PAGO), None)
        reconciliation = order.payment_reconciliation
        mp_status: Optional[TransactionStatusEnum] = mp.status if mp else None
        refund_requested = bool(
            mp and any(r.transaction_id == mp.id and r.gateway_ref_id for r in order.refunds)
        )
        actions: list[OrderAction] = []
        if is_cancelable(order.status):
            actions.append(OrderAction.CANCEL)
        if can_reconcile(mp_status, reconciliation.status if reconciliation else None):
            actions.append(OrderAction.RECONCILE)
        if (
            mp is not None
            and mp.gateway_ref_id
            and can_request_refund(
                order.status, mp_status, reconciliation is not None, refund_requested
            )
        ):
            actions.append(OrderAction.REQUEST_REFUND)
        history = sorted(order.history_logs, key=lambda h: h.created_at)
        return AdminOrderDetail(
            id=order.id,
            order_code=order.order_code,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            customer=AdminOrderCustomer.model_validate(data.customer),
            items=[
                AdminOrderItem.model_validate(i)
                for i in sorted(order.items, key=lambda i: i.product_name_snapshot)
            ],
            subtotal_amount=order.subtotal_amount,
            discount_amount=order.discount_amount,
            coupon_code=order.coupon_code,
            shipping_fee=order.shipping_fee,
            total_amount=order.total_amount,
            currency=order.currency,
            shipping_provider=order.shipping_provider,
            shipping_service_name=order.shipping_service_name,
            shipping_delivery_time_days=order.shipping_delivery_time_days,
            shipping_address_snapshot=order.shipping_address_snapshot,
            transactions=[AdminOrderTransaction.model_validate(t) for t in order.transactions],
            reconciliation=(
                AdminOrderReconciliation.model_validate(reconciliation) if reconciliation else None
            ),
            status_history=[
                AdminOrderStatusChange(
                    old_status=h.old_status,
                    new_status=h.new_status,
                    created_at=h.created_at,
                    changed_by=data.changed_by_names.get(h.changed_by_user_id)
                    if h.changed_by_user_id
                    else None,
                )
                for h in history
            ],
            allowed_actions=actions,
        )
