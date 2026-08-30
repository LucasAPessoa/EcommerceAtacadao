from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import Product, ProductVariant
from src.models.enums import (
    DiscountTypeEnum,
    OrderStatusEnum,
    PaymentMethodEnum,
    StockReservationStatusEnum,
)
from src.models.identity import Address
from src.models.operations import Transaction
from src.models.sales import (
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderItem,
    OrderStatusHistory,
    StockReservation,
)


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

    async def get_cart_for_checkout(self, user_id: UUID) -> Optional[Cart]:
        query = (
            select(Cart)
            .options(
                selectinload(Cart.items)
                .selectinload(CartItem.variant)
                .selectinload(ProductVariant.product)
                .selectinload(Product.pricing_tiers)
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
                .selectinload(ProductVariant.product)
                .selectinload(Product.pricing_tiers)
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
            .options(selectinload(ProductVariant.product).selectinload(Product.pricing_tiers))
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
