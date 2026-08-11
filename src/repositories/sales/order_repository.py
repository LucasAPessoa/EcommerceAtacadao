from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.enums import DiscountTypeEnum, OrderStatusEnum, PaymentMethodEnum
from src.models.identity import Address
from src.models.operations import Transaction
from src.models.sales import Coupon, Order, OrderItem, OrderStatusHistory


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
            selectinload(Order.items).selectinload(OrderItem.variant)
        )

    async def get_by_id(self, order_id: UUID) -> Optional[Order]:
        query = self._order_query().where(
            Order.id == order_id, Order.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, order_id: UUID, user_id: UUID) -> Optional[Order]:
        query = self._order_query().where(
            Order.id == order_id, Order.user_id == user_id, Order.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

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

    async def create_order(
        self,
        user_id: UUID,
        shipping_address_snapshot: dict,
        items: List[dict],
        coupon_code: Optional[str],
        discount_type: Optional[DiscountTypeEnum],
        discount_amount: float,
        shipping_fee: float,
        total_amount: float,
        payment_method: PaymentMethodEnum,
        installments: int,
    ) -> Order:
        order = Order(
            user_id=user_id,
            shipping_address_snapshot=shipping_address_snapshot,
            coupon_code=coupon_code,
            discount_type=discount_type,
            discount_amount=discount_amount,
            shipping_fee=shipping_fee,
            total_amount=total_amount,
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

    async def get_item_by_id(self, order_id: UUID, item_id: UUID) -> Optional[OrderItem]:
        query = select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.id == item_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_items(self, order_id: UUID) -> int:
        query = select(OrderItem).where(OrderItem.order_id == order_id)
        result = await self.session.execute(query)
        return len(result.scalars().all())

    async def update_item_quantity(self, item: OrderItem, quantity: int) -> None:
        item.quantity = quantity
        self.session.add(item)
        await self.session.flush()

    async def remove_item(self, item: OrderItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def update_address_snapshot(self, order: Order, snapshot: dict) -> None:
        order.shipping_address_snapshot = snapshot
        self.session.add(order)
        await self.session.flush()

    async def update_total_amount(self, order: Order, total_amount: float) -> None:
        order.total_amount = total_amount
        self.session.add(order)
        await self.session.flush()

    async def update_shipping_fee(self, order: Order, shipping_fee: float) -> None:
        order.shipping_fee = shipping_fee
        self.session.add(order)
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
