from collections import defaultdict
from typing import Optional
from uuid import UUID

from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.cart_repository import CartRepository
from src.schemas.sales.cart_schema import (
    CartItemCreateSchema,
    CartItemResponseSchema,
    CartItemUpdateSchema,
    CartResponseSchema,
)
from src.services.sales.pricing import select_unit_price


class CartService:
    def __init__(self, repository: CartRepository, variant_repository: ProductVariantRepository):
        self.repository = repository
        self.variant_repository = variant_repository

    @staticmethod
    def _response(cart) -> CartResponseSchema:
        """Monta totais informativos com a mesma faixa atacadista usada no checkout."""
        quantities_by_product = defaultdict(int)
        for item in cart.items:
            quantities_by_product[item.variant.product_id] += item.quantity

        items = []
        for item in cart.items:
            unit_price, _ = select_unit_price(
                item.variant, quantities_by_product[item.variant.product_id]
            )
            items.append(
                CartItemResponseSchema(
                    id=item.id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                    variant=item.variant,
                    unit_price=unit_price,
                )
            )
        return CartResponseSchema(
            id=cart.id,
            user_id=cart.user_id,
            created_at=cart.created_at,
            updated_at=cart.updated_at,
            items=items,
        )

    async def _get_or_create_cart(self, user_id: UUID):
        cart = await self.repository.get_by_user_id(user_id)
        if cart is None:
            cart = await self.repository.create_cart(user_id)
        return cart

    async def get_or_create_cart(self, user_id: UUID) -> CartResponseSchema:
        """Sempre devolve um carrinho (cria um vazio na primeira vez)."""
        cart = await self._get_or_create_cart(user_id)
        # Refetch com selectinload pra carregar `items` sem lazy-load
        # síncrono (que quebra em async session com MissingGreenlet).
        if cart is not None:
            cart = await self.repository.get_by_id(cart.id) or cart
        return self._response(cart)

    async def add_item(self, user_id: UUID, item_in: CartItemCreateSchema) -> CartResponseSchema:
        """
        Adiciona um item ao carrinho. Se a variação já estiver no carrinho,
        soma a quantidade em vez de criar uma linha duplicada.
        """
        variant = await self.variant_repository.get_by_id(item_in.variant_id)
        if not variant:
            raise ValueError("Variação de produto não encontrada.")
        if not variant.is_active:
            raise ValueError("Esta variação de produto não está disponível no momento.")

        cart = await self._get_or_create_cart(user_id)

        existing_item = await self.repository.get_item_by_variant(cart.id, item_in.variant_id)
        if existing_item:
            await self.repository.update_item_quantity(
                existing_item, existing_item.quantity + item_in.quantity
            )
        else:
            await self.repository.add_item(cart.id, item_in.variant_id, item_in.quantity)

        updated_cart = await self.repository.get_by_id(cart.id)
        return self._response(updated_cart)

    async def update_item_quantity(
        self, user_id: UUID, item_id: UUID, item_in: CartItemUpdateSchema
    ) -> Optional[CartResponseSchema]:
        cart = await self.repository.get_by_user_id(user_id)
        item = await self.repository.get_item_by_id(cart.id, item_id) if cart else None
        if not item:
            return None

        await self.repository.update_item_quantity(item, item_in.quantity)

        updated_cart = await self.repository.get_by_id(cart.id)
        return self._response(updated_cart)

    async def remove_item(self, user_id: UUID, item_id: UUID) -> Optional[CartResponseSchema]:
        cart = await self.repository.get_by_user_id(user_id)
        item = await self.repository.get_item_by_id(cart.id, item_id) if cart else None
        if not item:
            return None

        await self.repository.remove_item(item)

        updated_cart = await self.repository.get_by_id(cart.id)
        return self._response(updated_cart)

    async def clear_cart(self, user_id: UUID) -> CartResponseSchema:
        """Esvazia o carrinho (remove os itens, mantém o carrinho do usuário)."""
        cart = await self._get_or_create_cart(user_id)
        await self.repository.clear_items(cart.id)

        updated_cart = await self.repository.get_by_id(cart.id)
        return self._response(updated_cart)
