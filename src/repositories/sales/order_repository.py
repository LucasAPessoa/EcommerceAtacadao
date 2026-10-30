import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import ProductVariant
from src.models.enums import (
    DiscountTypeEnum,
    OrderStatusEnum,
    PaymentMethodEnum,
    ReconciliationReasonEnum,
    StockReservationStatusEnum,
    TransactionStatusEnum,
)
from src.models.identity import Address, User
from src.models.operations import PaymentReconciliation, Refund, Transaction
from src.models.sales import (
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderItem,
    OrderStatusHistory,
    StockReservation,
)
from src.repositories._like import escape_like

logger = logging.getLogger(__name__)


@dataclass
class AdminOrderFilters:
    statuses: list[OrderStatusEnum] = field(default_factory=list)
    # Limites já convertidos para UTC naive: created_at >= start e created_at < end.
    created_start: Optional[datetime] = None
    created_end: Optional[datetime] = None
    customer: Optional[str] = None


@dataclass
class AdminOrderDetailData:
    order: Order
    customer: User
    changed_by_names: dict[UUID, str]


class OrderRepository:
    """
    Repository dedicado do pedido (não estende BaseRepository): a criação
    é uma transação com múltiplas tabelas (Order + OrderItems + Transaction
    + histórico de status) e as consultas precisam vir sempre com
    itens/variante já carregados (selectinload).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def _order_query(self):
        return select(Order).options(
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.transactions),
            selectinload(Order.payment_reconciliation),
        )

    async def get_by_id(self, order_id: UUID) -> Optional[Order]:
        query = self._order_query().where(Order.id == order_id, Order.deleted_at.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, order_id: UUID, user_id: UUID) -> Optional[Order]:
        query = self._order_query().where(
            Order.id == order_id, Order.user_id == user_id, Order.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, user_id: UUID, key: UUID) -> Optional[Order]:
        query = self._order_query().where(
            Order.user_id == user_id,
            Order.checkout_idempotency_key == key,
            Order.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_order_status(self, order_id: UUID) -> Optional[OrderStatusEnum]:
        """Status atual lido do banco, ignorando o cache do identity map."""
        result = await self.session.execute(select(Order.status).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def get_transaction_for_order(self, order_id: UUID) -> Optional[Transaction]:
        query = select(Transaction).where(Transaction.order_id == order_id).with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_transaction_for_mercado_pago_order(self, order_id: UUID) -> Optional[Transaction]:
        query = (
            select(Transaction)
            .where(Transaction.order_id == order_id, Transaction.gateway_provider == "MERCADO_PAGO")
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_reconciliation_for_order(
        self, order_id: UUID, *, lock: bool = False
    ) -> Optional[PaymentReconciliation]:
        query = select(PaymentReconciliation).where(PaymentReconciliation.order_id == order_id)
        if lock:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_pending_reconciliations(
        self, skip: int = 0, limit: int = 100
    ) -> List[PaymentReconciliation]:
        from src.models.enums import ReconciliationStatusEnum

        result = await self.session.execute(
            select(PaymentReconciliation)
            .where(
                PaymentReconciliation.status.in_(
                    (ReconciliationStatusEnum.PENDING, ReconciliationStatusEnum.IN_REVIEW)
                )
            )
            .order_by(PaymentReconciliation.next_retry_at, PaymentReconciliation.created_at)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_reconciliation(
        self,
        order_id: UUID,
        transaction_id: UUID,
        now: datetime,
        *,
        reason: ReconciliationReasonEnum | None = None,
        error_code: str = "stock_commit_failed",
    ) -> PaymentReconciliation:
        from src.models.enums import ReconciliationStatusEnum

        reconciliation = PaymentReconciliation(
            order_id=order_id,
            transaction_id=transaction_id,
            status=ReconciliationStatusEnum.PENDING,
            reason=reason or ReconciliationReasonEnum.STOCK_COMMIT_FAILED,
            attempts=0,
            next_retry_at=now,
            last_error_code=error_code,
        )
        self.session.add(reconciliation)
        await self.session.flush()
        return reconciliation

    async def get_refund_for_reconciliation(self, transaction_id: UUID) -> Optional[Refund]:
        result = await self.session.execute(
            select(Refund).where(Refund.transaction_id == transaction_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_refund_for_transaction(self, transaction_id: UUID) -> Optional[Refund]:
        result = await self.session.execute(
            select(Refund).where(Refund.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def get_cart_for_checkout(self, user_id: UUID) -> Optional[Cart]:
        query = (
            select(Cart)
            .options(
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .options(
                    selectinload(ProductVariant.product),
                    selectinload(ProductVariant.pricing_tiers),
                )
            )
            .where(Cart.user_id == user_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def lock_cart_for_checkout(self, user_id: UUID) -> Optional[Cart]:
        query = (
            select(Cart)
            .options(
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .options(
                    selectinload(ProductVariant.product),
                    selectinload(ProductVariant.pricing_tiers),
                )
            )
            .where(Cart.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def lock_variants(self, variant_ids: List[UUID]) -> List[ProductVariant]:
        """Bloqueia SKUs em ordem estável para evitar overselling e deadlocks."""
        query = (
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product),
                selectinload(ProductVariant.pricing_tiers),
            )
            .where(
                ProductVariant.id.in_(sorted(variant_ids, key=str)),
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(ProductVariant.id)
            .with_for_update()
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_reserved_quantity(self, variant_id: UUID, now: datetime) -> int:
        query = select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(
            StockReservation.variant_id == variant_id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
            StockReservation.expires_at > now,
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_earliest_active_reservation_expiry(self, order_id: UUID) -> Optional[datetime]:
        query = select(func.min(StockReservation.expires_at)).where(
            StockReservation.order_id == order_id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_abandoned_order_ids(self, expired_before: datetime, limit: int) -> List[UUID]:
        """Pedidos aguardando pagamento cujas reservas ACTIVE venceram todas até `expired_before`
        (agora menos a tolerância da Order remota)."""
        now = expired_before
        expired = exists().where(
            StockReservation.order_id == Order.id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
            StockReservation.expires_at <= now,
        )
        live = exists().where(
            StockReservation.order_id == Order.id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
            StockReservation.expires_at > now,
        )
        query = (
            select(Order.id)
            .where(Order.status == OrderStatusEnum.PENDING_PAYMENT, expired, ~live)
            .order_by(Order.created_at)
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def list_stale_reservation_order_ids(self, now: datetime, limit: int) -> List[UUID]:
        """Pedidos CANCELED/EXPIRED que ainda mantêm reservas ACTIVE vencidas."""
        query = (
            select(StockReservation.order_id)
            .join(Order, Order.id == StockReservation.order_id)
            .where(
                StockReservation.status == StockReservationStatusEnum.ACTIVE,
                StockReservation.expires_at <= now,
                Order.status.in_([OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED]),
            )
            .distinct()
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def list_cancel_retry_order_ids(
        self, now: datetime, window_start: datetime, max_attempts: int, limit: int
    ) -> List[UUID]:
        """Pedidos CANCELED/EXPIRED com ref MP cujo cancel remoto segue sem confirmação."""
        canceled_in_window = exists().where(
            OrderStatusHistory.order_id == Order.id,
            OrderStatusHistory.new_status.in_([OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED]),
            OrderStatusHistory.created_at >= window_start,
        )
        query = (
            select(Order.id)
            .join(Transaction, Transaction.order_id == Order.id)
            .where(
                Order.status.in_([OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED]),
                Transaction.gateway_provider == "MERCADO_PAGO",
                Transaction.gateway_ref_id.is_not(None),
                Transaction.status != TransactionStatusEnum.APPROVED,
                Transaction.cancel_confirmed_at.is_(None),
                func.coalesce(Transaction.cancel_attempts, 0) < max_attempts,
                func.coalesce(Transaction.cancel_last_error_code, "") != "provider_terminal",
                canceled_in_window,
                # Backoff exponencial: 1, 2, 4, 8... minutos após a última tentativa.
                or_(
                    func.coalesce(Transaction.cancel_attempts, 0) == 0,
                    Transaction.cancel_last_attempt_at.is_(None),
                    Transaction.cancel_last_attempt_at
                    + func.power(2, Transaction.cancel_attempts - 1)
                    * literal_column("interval '1 minute'")
                    <= now,
                ),
            )
            .order_by(Order.created_at)
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def expire_active_reservations(self, order_id: UUID, now: datetime) -> int:
        """ACTIVE vencidas -> EXPIRED (terminal); devolve quantas mudaram."""
        query = (
            select(StockReservation)
            .where(
                StockReservation.order_id == order_id,
                StockReservation.status == StockReservationStatusEnum.ACTIVE,
                StockReservation.expires_at <= now,
            )
            .with_for_update()
        )
        reservations = list((await self.session.execute(query)).scalars().all())
        for reservation in reservations:
            reservation.status = StockReservationStatusEnum.EXPIRED
            reservation.released_at = now
            self.session.add(reservation)
        await self.session.flush()
        return len(reservations)

    async def count_live_active_reservations(self, order_id: UUID, now: datetime) -> int:
        query = select(func.count()).where(
            StockReservation.order_id == order_id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
            StockReservation.expires_at > now,
        )
        return int((await self.session.execute(query)).scalar_one())

    async def list_by_user(self, user_id: UUID, skip: int = 0, limit: int = 100) -> List[Order]:
        query = (
            self._order_query()
            .where(Order.user_id == user_id, Order.deleted_at.is_(None))
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[Order]:
        query = (
            self._order_query()
            .where(Order.deleted_at.is_(None))
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _admin_filtered(self, stmt, f: AdminOrderFilters):
        stmt = stmt.where(Order.deleted_at.is_(None))
        if f.statuses:
            stmt = stmt.where(Order.status.in_(f.statuses))
        if f.created_start is not None:
            stmt = stmt.where(Order.created_at >= f.created_start)
        if f.created_end is not None:
            stmt = stmt.where(Order.created_at < f.created_end)
        if f.customer and f.customer.strip():
            pattern = f"%{escape_like(f.customer.strip())}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                )
            )
        return stmt

    async def list_admin(
        self, filters: AdminOrderFilters, skip: int, limit: int
    ) -> tuple[list[tuple[Order, User, int]], int]:
        """Lista paginada para o portal admin e o total da consulta filtrada."""
        items_count = (
            select(func.count(OrderItem.id))
            .where(OrderItem.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )
        stmt = self._admin_filtered(
            select(Order, User, items_count).join(User, User.id == Order.user_id), filters
        )
        rows = await self.session.execute(
            stmt.order_by(Order.created_at.desc(), Order.id.desc()).offset(skip).limit(limit)
        )
        count_stmt = self._admin_filtered(
            select(func.count(Order.id)).select_from(Order).join(User, User.id == Order.user_id),
            filters,
        )
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return [(o, u, int(n)) for o, u, n in rows.all()], total

    async def get_admin_detail(self, order_id: UUID) -> Optional[AdminOrderDetailData]:
        query = (
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.transactions),
                selectinload(Order.payment_reconciliation),
                selectinload(Order.refunds),
                selectinload(Order.history_logs),
            )
            .where(Order.id == order_id, Order.deleted_at.is_(None))
        )
        order = (await self.session.execute(query)).scalar_one_or_none()
        if order is None:
            return None
        customer = await self.session.get(User, order.user_id)
        assert customer is not None
        author_ids = {h.changed_by_user_id for h in order.history_logs if h.changed_by_user_id}
        names: dict[UUID, str] = {}
        if author_ids:
            result = await self.session.execute(
                select(User.id, User.full_name).where(User.id.in_(author_ids))
            )
            names = {uid: name for uid, name in result.all()}
        return AdminOrderDetailData(order=order, customer=customer, changed_by_names=names)

    async def get_address_for_user(self, address_id: UUID, user_id: UUID) -> Optional[Address]:
        query = select(Address).where(
            Address.id == address_id, Address.user_id == user_id, Address.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_coupon(self, code: str) -> Optional[Coupon]:
        query = select(Coupon).where(
            Coupon.code == code, Coupon.is_active.is_(True), Coupon.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_checkout_order(
        self,
        user_id: UUID,
        shipping_address_snapshot: dict,
        items: List[dict],
        coupon_code: Optional[str],
        discount_type: Optional[DiscountTypeEnum],
        discount_amount: Decimal,
        shipping_fee: Decimal,
        total_amount: Decimal,
        subtotal_amount: Decimal,
        payment_method: PaymentMethodEnum,
        installments: int,
        checkout_idempotency_key: UUID,
        shipping_provider: str,
        shipping_service_id: Optional[int],
        shipping_service_name: Optional[str],
        shipping_delivery_time_days: Optional[int],
        reservation_expires_at: datetime,
    ) -> Order:
        order = Order(
            user_id=user_id,
            shipping_address_snapshot=shipping_address_snapshot,
            coupon_code=coupon_code,
            discount_type=discount_type,
            discount_amount=discount_amount,
            shipping_fee=shipping_fee,
            total_amount=total_amount,
            subtotal_amount=subtotal_amount,
            checkout_idempotency_key=checkout_idempotency_key,
            shipping_provider=shipping_provider,
            shipping_service_id=shipping_service_id,
            shipping_service_name=shipping_service_name,
            shipping_delivery_time_days=shipping_delivery_time_days,
        )
        self.session.add(order)
        await self.session.flush()  # gera order.id / order.order_code / order.status (default)

        for item in items:
            self.session.add(
                OrderItem(
                    order_id=order.id,
                    variant_id=item["variant_id"],
                    quantity=item["quantity"],
                    unit_price_snapshot=item["unit_price_snapshot"],
                    base_price_snapshot=item["base_price_snapshot"],
                    product_name_snapshot=item["product_name_snapshot"],
                    variation_name_snapshot=item["variation_name_snapshot"],
                    sku_snapshot=item["sku_snapshot"],
                    pricing_tier_min_quantity=item["pricing_tier_min_quantity"],
                    logistics_snapshot=item["logistics_snapshot"],
                )
            )
            self.session.add(
                StockReservation(
                    order_id=order.id,
                    variant_id=item["variant_id"],
                    quantity=item["quantity"],
                    expires_at=reservation_expires_at,
                )
            )

        self.session.add(
            Transaction(
                order_id=order.id,
                payment_method=payment_method,
                amount=total_amount,
                installments=installments,
            )
        )

        self.session.add(
            OrderStatusHistory(
                order_id=order.id,
                old_status=None,
                new_status=order.status,
                changed_by_user_id=user_id,
            )
        )

        await self.session.flush()
        return order

    async def clear_cart(self, cart: Cart) -> None:
        for item in list(cart.items):
            await self.session.delete(item)
        await self.session.flush()

    async def release_active_reservations(self, order_id: UUID, released_at: datetime) -> None:
        query = select(StockReservation).where(
            StockReservation.order_id == order_id,
            StockReservation.status == StockReservationStatusEnum.ACTIVE,
        )
        result = await self.session.execute(query)
        for reservation in result.scalars().all():
            reservation.status = StockReservationStatusEnum.RELEASED
            reservation.released_at = released_at
            self.session.add(reservation)
        await self.session.flush()

    async def confirm_active_reservations(self, order_id: UUID, confirmed_at: datetime) -> None:
        query = (
            select(StockReservation)
            .where(
                StockReservation.order_id == order_id,
                StockReservation.status == StockReservationStatusEnum.ACTIVE,
            )
            .with_for_update()
        )
        reservations = list((await self.session.execute(query)).scalars().all())
        variant_ids = [reservation.variant_id for reservation in reservations]
        variants = await self.lock_variants(variant_ids)
        variants_by_id = {variant.id: variant for variant in variants}
        for reservation in reservations:
            variant = variants_by_id.get(reservation.variant_id)
            if (
                variant is None
                or reservation.expires_at <= confirmed_at
                or variant.stock_quantity < reservation.quantity
            ):
                raise ValueError(
                    "Reserva expirada ou estoque indisponível para confirmar pagamento."
                )
        for reservation in reservations:
            variant = variants_by_id[reservation.variant_id]
            variant.stock_quantity -= reservation.quantity
            reservation.status = StockReservationStatusEnum.CONFIRMED
            reservation.confirmed_at = confirmed_at
        await self.session.flush()

    async def restore_confirmed_stock(self, order_id: UUID, restored_at: datetime) -> None:
        """Devolve o estoque baixado por confirm_active_reservations, uma única vez.

        Não há movimento de inventário: a baixa é um decremento de
        ``stock_quantity`` com a reserva marcada CONFIRMED. Reverter é incrementar
        e marcar a reserva RELEASED, o que torna a operação idempotente.
        """
        query = (
            select(StockReservation)
            .where(
                StockReservation.order_id == order_id,
                StockReservation.status == StockReservationStatusEnum.CONFIRMED,
            )
            .with_for_update()
        )
        reservations = list((await self.session.execute(query)).scalars().all())
        if not reservations:
            return
        variants = await self.lock_variants([r.variant_id for r in reservations])
        variants_by_id = {variant.id: variant for variant in variants}
        for reservation in reservations:
            variant = variants_by_id.get(reservation.variant_id)
            if variant is not None:
                variant.stock_quantity += reservation.quantity
            else:
                # Política atual: lock_variants ignora SKU excluído, então não há
                # estoque a devolver; a reserva ainda é liberada.
                logger.warning(
                    "stock_restore_skipped_deleted_sku reservation_id=%s", reservation.id
                )
            reservation.status = StockReservationStatusEnum.RELEASED
            reservation.released_at = restored_at
        await self.session.flush()

    async def update_status(
        self, order: Order, new_status: OrderStatusEnum, changed_by_user_id: Optional[UUID]
    ) -> None:
        old_status = order.status
        order.status = new_status
        self.session.add(order)
        self.session.add(
            OrderStatusHistory(
                order_id=order.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_user_id=changed_by_user_id,
            )
        )
        await self.session.flush()
