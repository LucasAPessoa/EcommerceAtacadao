from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.catalog import ProductVariant
from src.models.enums import DiscountTypeEnum
from src.models.identity import Address
from src.models.sales import Cart, Coupon
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.checkout_schema import (
    CheckoutConfirmSchema,
    CheckoutItemPreviewSchema,
    CheckoutPreviewRequestSchema,
    CheckoutPreviewResponseSchema,
    CheckoutShippingOptionSchema,
)
from src.schemas.sales.order_schema import OrderResponseSchema
from src.services.operations.shipping_service import ShippingService

MONEY_QUANTUM = Decimal("0.01")


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _address_snapshot(address: Address) -> Dict[str, Any]:
    return {
        "zip_code": address.zip_code,
        "street": address.street,
        "number": address.number,
        "complement": address.complement,
        "neighborhood": address.neighborhood,
        "city": address.city,
        "state": address.state,
    }


class CheckoutService:
    """Coordena o checkout sem delegar a atomicidade a repositories isolados."""

    def __init__(
        self,
        session: AsyncSession,
        repository: OrderRepository,
        shipping_service: ShippingService,
    ) -> None:
        self.session = session
        self.repository = repository
        self.shipping_service = shipping_service

    @staticmethod
    def _cart_fingerprint(cart: Cart) -> Tuple[Tuple[str, int], ...]:
        return tuple(sorted((str(item.variant_id), item.quantity) for item in cart.items))

    @staticmethod
    def _ensure_cart(cart: Optional[Cart]) -> Cart:
        if cart is None or not cart.items:
            raise ValueError("O carrinho está vazio.")
        return cart

    @staticmethod
    def _select_unit_price(
        variant: ProductVariant, product_quantity: int
    ) -> Tuple[Decimal, Optional[int]]:
        base_price = _money(variant.base_price)
        applicable = [
            tier for tier in variant.product.pricing_tiers if tier.min_quantity <= product_quantity
        ]
        if not applicable:
            return base_price, None
        tier = max(applicable, key=lambda current: current.min_quantity)
        return _money(tier.unit_price), tier.min_quantity

    def _build_lines(
        self,
        cart: Cart,
        variants_by_id: Optional[Dict[UUID, ProductVariant]] = None,
    ) -> Tuple[List[Dict[str, Any]], Decimal]:
        quantities_by_product: Dict[UUID, int] = defaultdict(int)
        for item in cart.items:
            variant = variants_by_id.get(item.variant_id) if variants_by_id else item.variant
            if variant is None:
                raise ValueError(f"Variação {item.variant_id} não encontrada.")
            quantities_by_product[variant.product_id] += item.quantity

        lines: List[Dict[str, Any]] = []
        subtotal = Decimal("0.00")
        for item in cart.items:
            variant = variants_by_id.get(item.variant_id) if variants_by_id else item.variant
            if variant is None or not variant.is_active or not variant.product.is_active:
                raise ValueError("Um dos produtos do carrinho não está mais disponível.")

            unit_price, tier_quantity = self._select_unit_price(
                variant, quantities_by_product[variant.product_id]
            )
            line_subtotal = _money(unit_price * item.quantity)
            subtotal += line_subtotal
            lines.append(
                {
                    "variant_id": variant.id,
                    "variant": variant,
                    "quantity": item.quantity,
                    "base_price_snapshot": _money(variant.base_price),
                    "unit_price_snapshot": unit_price,
                    "product_name_snapshot": variant.product.name,
                    "variation_name_snapshot": variant.variation_name,
                    "sku_snapshot": variant.bling_sku,
                    "pricing_tier_min_quantity": tier_quantity,
                    "logistics_snapshot": {
                        "weight_kg": variant.weight_kg,
                        "height_cm": variant.height_cm,
                        "width_cm": variant.width_cm,
                        "length_cm": variant.length_cm,
                    },
                    "subtotal": line_subtotal,
                }
            )
        return lines, _money(subtotal)

    @staticmethod
    def _validate_coupon(coupon: Coupon, subtotal: Decimal) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        if coupon.expires_at and coupon.expires_at < now:
            raise ValueError("Este cupom já expirou.")
        if coupon.min_order_amount and subtotal < _money(coupon.min_order_amount):
            raise ValueError(
                f"Pedido mínimo de R$ {_money(coupon.min_order_amount):.2f} para usar este cupom."
            )

    def _calculate_discount(
        self,
        coupon: Optional[Coupon],
        subtotal: Decimal,
        shipping_fee: Decimal,
    ) -> Decimal:
        if coupon is None:
            return Decimal("0.00")
        self._validate_coupon(coupon, subtotal)
        if coupon.discount_type == DiscountTypeEnum.PERCENTAGE:
            return _money(subtotal * (_money(coupon.discount_value) / Decimal("100")))
        if coupon.discount_type == DiscountTypeEnum.FIXED_AMOUNT:
            return min(_money(coupon.discount_value), subtotal)
        if coupon.discount_type == DiscountTypeEnum.FREE_SHIPPING:
            return shipping_fee
        return Decimal("0.00")

    async def _coupon(self, code: Optional[str]) -> Optional[Coupon]:
        if not code:
            return None
        coupon = await self.repository.get_active_coupon(code)
        if coupon is None:
            raise ValueError("Cupom inválido ou inexistente.")
        return coupon

    async def _shipping_options(
        self,
        address: Address,
        lines: Iterable[Dict[str, Any]],
    ):
        products = [
            ShippingService.build_product_item(
                line["variant"], line["quantity"], line["unit_price_snapshot"]
            )
            for line in lines
        ]
        quotes = await self.shipping_service.calculate_quotes_for_products(
            origin_zip_code=settings.STORE_ORIGIN_ZIP_CODE,
            destination_zip_code=address.zip_code,
            products=products,
        )
        if not quotes:
            raise ValueError("Não foi possível calcular o frete para este endereço.")
        return quotes

    async def preview(
        self, user_id: UUID, checkout_in: CheckoutPreviewRequestSchema
    ) -> CheckoutPreviewResponseSchema:
        cart = self._ensure_cart(await self.repository.get_cart_for_checkout(user_id))
        address = await self.repository.get_address_for_user(checkout_in.address_id, user_id)
        if address is None:
            raise ValueError("Endereço não encontrado para este usuário.")

        lines, subtotal = self._build_lines(cart)
        coupon = await self._coupon(checkout_in.coupon_code)
        quotes = await self._shipping_options(address, lines)

        options: List[CheckoutShippingOptionSchema] = []
        for quote in quotes:
            if quote.service_id is None:
                continue
            shipping_fee = _money(quote.price)
            discount = self._calculate_discount(coupon, subtotal, shipping_fee)
            options.append(
                CheckoutShippingOptionSchema(
                    service_id=quote.service_id,
                    service_name=quote.service_name,
                    company_name=quote.company_name,
                    price=shipping_fee,
                    delivery_time_days=quote.delivery_time_days,
                    discount_amount=discount,
                    total_amount=_money(max(subtotal + shipping_fee - discount, Decimal("0"))),
                )
            )

        if not options:
            raise ValueError("Nenhuma opção de frete válida foi encontrada.")

        return CheckoutPreviewResponseSchema(
            items=[
                CheckoutItemPreviewSchema(
                    variant_id=line["variant_id"],
                    product_name=line["product_name_snapshot"],
                    variation_name=line["variation_name_snapshot"],
                    sku=line["sku_snapshot"],
                    quantity=line["quantity"],
                    base_unit_price=line["base_price_snapshot"],
                    unit_price=line["unit_price_snapshot"],
                    pricing_tier_min_quantity=line["pricing_tier_min_quantity"],
                    subtotal=line["subtotal"],
                )
                for line in lines
            ],
            subtotal_amount=subtotal,
            coupon_code=checkout_in.coupon_code,
            discount_type=coupon.discount_type if coupon else None,
            shipping_options=options,
        )

    async def confirm(
        self, user_id: UUID, checkout_in: CheckoutConfirmSchema, idempotency_key: UUID
    ) -> OrderResponseSchema:
        existing = await self.repository.get_by_idempotency_key(user_id, idempotency_key)
        if existing is not None:
            return OrderResponseSchema.model_validate(existing)

        cart = self._ensure_cart(await self.repository.get_cart_for_checkout(user_id))
        initial_fingerprint = self._cart_fingerprint(cart)
        address = await self.repository.get_address_for_user(checkout_in.address_id, user_id)
        if address is None:
            raise ValueError("Endereço não encontrado para este usuário.")
        initial_lines, _ = self._build_lines(cart)
        quotes = await self._shipping_options(address, initial_lines)
        selected_quote = next(
            (quote for quote in quotes if quote.service_id == checkout_in.shipping_service_id),
            None,
        )
        if selected_quote is None:
            raise ValueError("A opção de frete selecionada não está mais disponível.")

        # As leituras e a chamada externa acima não devem manter locks. A
        # partir daqui começa a unidade atômica que será commitada por get_db.
        await self.session.rollback()

        locked_cart = await self.repository.lock_cart_for_checkout(user_id)
        existing = await self.repository.get_by_idempotency_key(user_id, idempotency_key)
        if existing is not None:
            return OrderResponseSchema.model_validate(existing)
        locked_cart = self._ensure_cart(locked_cart)
        if self._cart_fingerprint(locked_cart) != initial_fingerprint:
            raise ValueError(
                "O carrinho foi alterado durante o checkout. Revise e tente novamente."
            )

        variant_ids = [item.variant_id for item in locked_cart.items]
        locked_variants = await self.repository.lock_variants(variant_ids)
        variants_by_id = {variant.id: variant for variant in locked_variants}
        if len(variants_by_id) != len(set(variant_ids)):
            raise ValueError("Um dos produtos do carrinho não está mais disponível.")

        lines, subtotal = self._build_lines(locked_cart, variants_by_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        for line in lines:
            variant = variants_by_id[line["variant_id"]]
            reserved = await self.repository.get_active_reserved_quantity(variant.id, now)
            available = variant.stock_quantity - reserved
            if line["quantity"] > available:
                raise ValueError(
                    f"Estoque insuficiente para '{variant.variation_name}'. "
                    f"Disponível: {max(available, 0)}."
                )

        address = await self.repository.get_address_for_user(checkout_in.address_id, user_id)
        if address is None:
            raise ValueError("Endereço não encontrado para este usuário.")
        coupon = await self._coupon(checkout_in.coupon_code)
        shipping_fee = _money(selected_quote.price)
        discount = self._calculate_discount(coupon, subtotal, shipping_fee)
        total = _money(max(subtotal + shipping_fee - discount, Decimal("0")))
        if total != _money(checkout_in.expected_total_amount):
            raise ValueError(
                "O preço ou o frete mudou desde a simulação. Revise o checkout antes de confirmar."
            )

        order = await self.repository.create_checkout_order(
            user_id=user_id,
            shipping_address_snapshot=_address_snapshot(address),
            items=lines,
            coupon_code=checkout_in.coupon_code,
            discount_type=coupon.discount_type if coupon else None,
            discount_amount=discount,
            shipping_fee=shipping_fee,
            total_amount=total,
            subtotal_amount=subtotal,
            payment_method=checkout_in.payment_method,
            installments=checkout_in.installments,
            checkout_idempotency_key=idempotency_key,
            shipping_provider=selected_quote.company_name or "Melhor Envio",
            shipping_service_id=selected_quote.service_id,
            shipping_service_name=selected_quote.service_name,
            shipping_delivery_time_days=selected_quote.delivery_time_days,
            reservation_expires_at=now + timedelta(minutes=settings.STOCK_RESERVATION_MINUTES),
        )
        await self.repository.clear_cart(locked_cart)
        created = await self.repository.get_by_id(order.id)
        return OrderResponseSchema.model_validate(created)
