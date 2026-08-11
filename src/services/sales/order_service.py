from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from src.core.config import settings
from src.integrations.melhor_envio.schemas import MelhorEnvioProductItem
from src.models.enums import DiscountTypeEnum, OrderStatusEnum
from src.models.identity import Address, User
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.order_schema import OrderCreateSchema, OrderResponseSchema
from src.services.operations.shipping_service import ShippingService

# Só dá pra editar itens/endereço enquanto o pedido está pendente.
EDITABLE_STATUSES = {OrderStatusEnum.PENDING}

# Pode cancelar em qualquer status ANTERIOR ao envio.
CANCELABLE_STATUSES = {OrderStatusEnum.PENDING, OrderStatusEnum.APPROVED, OrderStatusEnum.PREPARING}


def _snapshot_address(address: Address) -> dict:
    return {
        "zip_code": address.zip_code,
        "street": address.street,
        "number": address.number,
        "complement": address.complement,
        "neighborhood": address.neighborhood,
        "city": address.city,
        "state": address.state,
    }


def _is_admin(user: User) -> bool:
    return getattr(user.role, "name", None) == "admin"


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        variant_repository: ProductVariantRepository,
        shipping_service: ShippingService,
    ):
        self.repository = repository
        self.variant_repository = variant_repository
        self.shipping_service = shipping_service

    async def _build_items(self, items_in) -> tuple[List[dict], float]:
        """Valida cada variação e monta os itens com o preço já 'congelado' (snapshot)."""
        items: List[dict] = []
        subtotal = 0.0
        for item_in in items_in:
            variant = await self.variant_repository.get_by_id(item_in.variant_id)
            if not variant:
                raise ValueError(f"Variação {item_in.variant_id} não encontrada.")
            if not variant.is_active:
                raise ValueError(f"Variação '{variant.variation_name}' não está disponível no momento.")

            unit_price = float(variant.base_price)
            items.append(
                {
                    "variant_id": item_in.variant_id,
                    "quantity": item_in.quantity,
                    "unit_price_snapshot": unit_price,
                    # Guardado só pra montar a cotação de frete sem buscar a
                    # variante de novo (ShippingService.build_product_item) —
                    # não é persistido pelo repository.create_order.
                    "_shipping_product": ShippingService.build_product_item(variant, item_in.quantity),
                }
            )
            subtotal += unit_price * item_in.quantity

        return items, round(subtotal, 2)

    async def _calculate_shipping_fee(self, destination_zip_code: str, items: List[dict]) -> float:
        products = [item["_shipping_product"] for item in items]
        return await self.shipping_service.get_cheapest_fee_for_products(
            origin_zip_code=settings.STORE_ORIGIN_ZIP_CODE,
            destination_zip_code=destination_zip_code,
            products=products,
        )

    def _apply_coupon(self, coupon, subtotal: float, shipping_fee: float) -> float:
        """Calcula o desconto e devolve o valor a abater (do subtotal ou do frete)."""
        now = datetime.now(timezone.utc)
        if coupon.expires_at and coupon.expires_at.replace(tzinfo=timezone.utc) < now:
            raise ValueError("Este cupom já expirou.")
        if coupon.min_order_amount and subtotal < float(coupon.min_order_amount):
            raise ValueError(
                f"Pedido mínimo de R$ {float(coupon.min_order_amount):.2f} para usar este cupom."
            )

        if coupon.discount_type == DiscountTypeEnum.PERCENTAGE:
            return round(subtotal * (float(coupon.discount_value) / 100), 2)
        if coupon.discount_type == DiscountTypeEnum.FIXED_AMOUNT:
            return round(min(float(coupon.discount_value), subtotal), 2)
        if coupon.discount_type == DiscountTypeEnum.FREE_SHIPPING:
            # Abate exatamente o valor do frete calculado, zerando-o no total
            # (fica registrado em discount_amount pra dar pra ver quanto o
            # cliente "economizou", em vez de simplesmente sumir com o frete).
            return round(shipping_fee, 2)
        return 0.0

    async def create_order(self, user_id: UUID, order_in: OrderCreateSchema) -> OrderResponseSchema:
        address = await self.repository.get_address_for_user(order_in.address_id, user_id)
        if not address:
            raise ValueError("Endereço não encontrado para este usuário.")

        items, subtotal = await self._build_items(order_in.items)

        shipping_fee = await self._calculate_shipping_fee(address.zip_code, items)

        discount_type: Optional[DiscountTypeEnum] = None
        discount_amount = 0.0
        if order_in.coupon_code:
            coupon = await self.repository.get_active_coupon(order_in.coupon_code)
            if not coupon:
                raise ValueError("Cupom inválido ou inexistente.")
            discount_amount = self._apply_coupon(coupon, subtotal, shipping_fee)
            discount_type = coupon.discount_type

        total_amount = max(round(subtotal - discount_amount + shipping_fee, 2), 0.0)

        order = await self.repository.create_order(
            user_id=user_id,
            shipping_address_snapshot=_snapshot_address(address),
            items=items,
            coupon_code=order_in.coupon_code,
            discount_type=discount_type,
            discount_amount=discount_amount,
            shipping_fee=shipping_fee,
            total_amount=total_amount,
            payment_method=order_in.payment_method,
            installments=order_in.installments,
        )

        created = await self.repository.get_by_id(order.id)
        return OrderResponseSchema.model_validate(created)

    async def get_order(self, order_id: UUID, current_user: User) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if not order:
            return None
        return OrderResponseSchema.model_validate(order)

    async def list_orders(
        self, current_user: User, skip: int = 0, limit: int = 100
    ) -> List[OrderResponseSchema]:
        if _is_admin(current_user):
            orders = await self.repository.list_all(skip=skip, limit=limit)
        else:
            orders = await self.repository.list_by_user(current_user.id, skip=skip, limit=limit)
        return [OrderResponseSchema.model_validate(o) for o in orders]

    async def _recalculate_total(self, order) -> None:
        subtotal = sum(float(item.unit_price_snapshot) * item.quantity for item in order.items)
        total = max(round(subtotal - float(order.discount_amount) + float(order.shipping_fee), 2), 0.0)
        await self.repository.update_total_amount(order, total)

    async def update_item_quantity(
        self, user_id: UUID, order_id: UUID, item_id: UUID, quantity: int
    ) -> Optional[OrderResponseSchema]:
        order = await self.repository.get_by_id_for_user(order_id, user_id)
        if not order:
            return None
        if order.status not in EDITABLE_STATUSES:
            raise ValueError("Este pedido não pode mais ser editado (só é possível enquanto está pendente).")

        item = await self.repository.get_item_by_id(order_id, item_id)
        if not item:
            return None

        await self.repository.update_item_quantity(item, quantity)

        updated = await self.repository.get_by_id(order_id)
        await self._recalculate_total(updated)
        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)

    async def remove_item(
        self, user_id: UUID, order_id: UUID, item_id: UUID
    ) -> Optional[OrderResponseSchema]:
        order = await self.repository.get_by_id_for_user(order_id, user_id)
        if not order:
            return None
        if order.status not in EDITABLE_STATUSES:
            raise ValueError("Este pedido não pode mais ser editado (só é possível enquanto está pendente).")

        item = await self.repository.get_item_by_id(order_id, item_id)
        if not item:
            return None
        if await self.repository.count_items(order_id) <= 1:
            raise ValueError("O pedido precisa ter ao menos um item — cancele o pedido em vez de esvaziá-lo.")

        await self.repository.remove_item(item)

        updated = await self.repository.get_by_id(order_id)
        await self._recalculate_total(updated)
        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)

    async def update_address(
        self, user_id: UUID, order_id: UUID, address_id: UUID
    ) -> Optional[OrderResponseSchema]:
        order = await self.repository.get_by_id_for_user(order_id, user_id)
        if not order:
            return None
        if order.status not in EDITABLE_STATUSES:
            raise ValueError(
                "O endereço só pode ser alterado enquanto o pedido está pendente."
            )

        address = await self.repository.get_address_for_user(address_id, user_id)
        if not address:
            raise ValueError("Endereço não encontrado para este usuário.")

        await self.repository.update_address_snapshot(order, _snapshot_address(address))

        # Mudou o destino -> o frete muda junto. O desconto de cupom (se
        # houver) fica congelado no valor calculado na criação do pedido,
        # só o frete e o total são recalculados aqui. `order.items[].variant`
        # já veio carregado (selectinload), então não precisa buscar de novo.
        shipping_products = [
            ShippingService.build_product_item(item.variant, item.quantity) for item in order.items
        ]
        new_shipping_fee = await self.shipping_service.get_cheapest_fee_for_products(
            origin_zip_code=settings.STORE_ORIGIN_ZIP_CODE,
            destination_zip_code=address.zip_code,
            products=shipping_products,
        )
        await self.repository.update_shipping_fee(order, new_shipping_fee)

        subtotal = sum(float(item.unit_price_snapshot) * item.quantity for item in order.items)
        new_total = max(round(subtotal - float(order.discount_amount) + new_shipping_fee, 2), 0.0)
        await self.repository.update_total_amount(order, new_total)

        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)

    async def cancel_order(self, order_id: UUID, current_user: User) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if not order:
            return None

        if order.status not in CANCELABLE_STATUSES:
            raise ValueError(
                "Este pedido não pode mais ser cancelado (já foi enviado, entregue ou já está cancelado)."
            )

        await self.repository.update_status(order, OrderStatusEnum.CANCELED, current_user.id)

        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)
