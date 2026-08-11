from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.sales import Cart, CartItem


class CartRepository:
    """
    Repository dedicado do carrinho. Não estende BaseRepository porque o
    carrinho não é um CRUD simples por ID: as operações reais são
    "pegar (ou criar) o carrinho do usuário" e "mexer nos itens dele",
    sempre trazendo `items` + `variant` já carregados (selectinload) pra
    montar o CartResponseSchema sem N+1 query.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def _cart_query(self):
        return select(Cart).options(
            selectinload(Cart.items).selectinload(CartItem.variant)
        )

    async def get_by_user_id(self, user_id: UUID) -> Optional[Cart]:
        query = self._cart_query().where(Cart.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, cart_id: UUID) -> Optional[Cart]:
        query = self._cart_query().where(Cart.id == cart_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_cart(self, user_id: UUID) -> Cart:
        cart = Cart(user_id=user_id)
        self.session.add(cart)
        await self.session.flush()
        cart.items = []  # carrinho recém-criado, sem itens ainda
        return cart

    async def get_item_by_variant(self, cart_id: UUID, variant_id: UUID) -> Optional[CartItem]:
        query = select(CartItem).where(
            CartItem.cart_id == cart_id, CartItem.variant_id == variant_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_item_by_id(self, cart_id: UUID, item_id: UUID) -> Optional[CartItem]:
        query = select(CartItem).where(
            CartItem.cart_id == cart_id, CartItem.id == item_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_item(self, cart_id: UUID, variant_id: UUID, quantity: int) -> None:
        item = CartItem(cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        self.session.add(item)
        await self.session.flush()

    async def update_item_quantity(self, item: CartItem, quantity: int) -> None:
        item.quantity = quantity
        self.session.add(item)
        await self.session.flush()

    async def remove_item(self, item: CartItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def clear_items(self, cart_id: UUID) -> None:
        query = select(CartItem).where(CartItem.cart_id == cart_id)
        result = await self.session.execute(query)
        for item in result.scalars().all():
            await self.session.delete(item)
        await self.session.flush()
