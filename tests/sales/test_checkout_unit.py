from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import DiscountTypeEnum, PaymentMethodEnum
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
from src.schemas.sales.order_schema import OrderResponseSchema
from src.services.sales.checkout_service import CheckoutService


def _variant(*, stock: int = 20):
    product_id = uuid4()
    product = SimpleNamespace(
        id=product_id,
        name="Produto atacadista",
        is_active=True,
        pricing_tiers=[
            SimpleNamespace(min_quantity=5, unit_price=Decimal("8.50")),
            SimpleNamespace(min_quantity=10, unit_price=Decimal("7.25")),
        ],
    )
    return SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        product=product,
        base_price=Decimal("10.00"),
        stock_quantity=stock,
        is_active=True,
        variation_name="Caixa",
        bling_sku="SKU-CAIXA",
        weight_kg=1.0,
        height_cm=10.0,
        width_cm=10.0,
        length_cm=10.0,
    )


def _service(repository=None, shipping_service=None, session=None):
    return CheckoutService(
        session=session or AsyncMock(),
        repository=repository or AsyncMock(),
        shipping_service=shipping_service or AsyncMock(),
    )


def test_build_lines_applies_highest_wholesale_tier() -> None:
    variant = _variant()
    cart = SimpleNamespace(
        items=[SimpleNamespace(variant_id=variant.id, variant=variant, quantity=12)]
    )

    lines, subtotal = _service()._build_lines(cart)

    assert lines[0]["base_price_snapshot"] == Decimal("10.00")
    assert lines[0]["unit_price_snapshot"] == Decimal("7.25")
    assert lines[0]["pricing_tier_min_quantity"] == 10
    assert subtotal == Decimal("87.00")


@pytest.mark.parametrize(
    ("payment_method", "installments"),
    [
        (PaymentMethodEnum.PIX, 1),
        (PaymentMethodEnum.BOLETO, 1),
        (PaymentMethodEnum.CREDIT_CARD, 1),
        (PaymentMethodEnum.CREDIT_CARD, 12),
    ],
)
def test_checkout_accepts_supported_payment_shapes(
    payment_method: PaymentMethodEnum, installments: int
) -> None:
    checkout = CheckoutConfirmSchema(
        address_id=uuid4(),
        shipping_service_id=1,
        expected_total_amount=Decimal("10.00"),
        payment_method=payment_method,
        installments=installments,
    )

    assert checkout.payment_method == payment_method
    assert checkout.installments == installments


@pytest.mark.parametrize(
    ("discount_type", "discount_value", "subtotal", "shipping", "expected"),
    [
        (DiscountTypeEnum.PERCENTAGE, "10.00", "100.00", "20.00", "10.00"),
        (DiscountTypeEnum.FIXED_AMOUNT, "15.00", "100.00", "20.00", "15.00"),
        (DiscountTypeEnum.FREE_SHIPPING, "0.00", "100.00", "20.00", "20.00"),
    ],
)
def test_checkout_calculates_every_discount_type(
    discount_type: DiscountTypeEnum,
    discount_value: str,
    subtotal: str,
    shipping: str,
    expected: str,
) -> None:
    coupon = SimpleNamespace(
        discount_type=discount_type,
        discount_value=Decimal(discount_value),
        min_order_amount=None,
        expires_at=None,
    )

    discount = _service()._calculate_discount(
        coupon, Decimal(subtotal), Decimal(shipping)
    )

    assert discount == Decimal(expected)


def _order_response(user_id, order_id=None) -> OrderResponseSchema:
    now = datetime.now(UTC).replace(tzinfo=None)
    return OrderResponseSchema.model_construct(
        id=order_id or uuid4(),
        order_code="PED-TEST-0001",
        user_id=user_id,
        status="PENDING_PAYMENT",
        shipping_address_snapshot={},
        checkout_idempotency_key=uuid4(),
        coupon_code=None,
        discount_type=None,
        subtotal_amount=Decimal("20.00"),
        discount_amount=Decimal("0.00"),
        shipping_fee=Decimal("20.00"),
        total_amount=Decimal("40.00"),
        currency="BRL",
        shipping_provider="Correios",
        shipping_service_id=1,
        shipping_service_name="PAC",
        shipping_delivery_time_days=5,
        items=[],
        transactions=[],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_confirm_creates_order_and_clears_cart_atomically() -> None:
    user_id = uuid4()
    address_id = uuid4()
    variant = _variant(stock=5)
    item = SimpleNamespace(variant_id=variant.id, variant=variant, quantity=2)
    cart = SimpleNamespace(id=uuid4(), items=[item])
    address = SimpleNamespace(
        id=address_id,
        zip_code="01001000",
        street="Rua A",
        number="1",
        complement=None,
        neighborhood="Centro",
        city="São Paulo",
        state="SP",
    )
    quote = SimpleNamespace(
        service_id=1,
        service_name="PAC",
        company_name="Correios",
        price=Decimal("20.00"),
        delivery_time_days=5,
    )
    repository = AsyncMock()
    repository.get_by_idempotency_key.side_effect = [None, None]
    repository.get_cart_for_checkout.return_value = cart
    repository.get_address_for_user.return_value = address
    repository.lock_cart_for_checkout.return_value = cart
    repository.lock_variants.return_value = [variant]
    repository.get_active_reserved_quantity.return_value = 0
    created_id = uuid4()
    repository.create_checkout_order.return_value = SimpleNamespace(id=created_id)
    repository.get_by_id.return_value = _order_response(user_id, created_id)
    shipping_service = AsyncMock()
    shipping_service.calculate_quotes_for_products.return_value = [quote]
    session = AsyncMock()
    service = _service(repository, shipping_service, session)

    result = await service.confirm(
        user_id,
        CheckoutConfirmSchema(
            address_id=address_id,
            shipping_service_id=1,
            expected_total_amount=Decimal("40.00"),
            payment_method=PaymentMethodEnum.PIX,
            installments=1,
        ),
        uuid4(),
    )

    assert result.id == created_id
    session.rollback.assert_awaited_once()
    repository.create_checkout_order.assert_awaited_once()
    repository.clear_cart.assert_awaited_once_with(cart)


@pytest.mark.asyncio
async def test_confirm_replays_existing_order_for_same_idempotency_key() -> None:
    user_id = uuid4()
    existing = _order_response(user_id)
    repository = AsyncMock()
    repository.get_by_idempotency_key.return_value = existing
    service = _service(repository=repository)

    result = await service.confirm(
        user_id,
        CheckoutConfirmSchema(
            address_id=uuid4(),
            shipping_service_id=1,
            expected_total_amount=Decimal("40.00"),
            payment_method=PaymentMethodEnum.PIX,
            installments=1,
        ),
        uuid4(),
    )

    assert result.id == existing.id
    repository.get_cart_for_checkout.assert_not_awaited()
    repository.create_checkout_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_rejects_quantity_already_reserved() -> None:
    user_id = uuid4()
    address_id = uuid4()
    variant = _variant(stock=5)
    cart = SimpleNamespace(
        items=[SimpleNamespace(variant_id=variant.id, variant=variant, quantity=2)]
    )
    address = SimpleNamespace(
        id=address_id,
        zip_code="01001000",
        street="Rua A",
        number="1",
        complement=None,
        neighborhood="Centro",
        city="São Paulo",
        state="SP",
    )
    quote = SimpleNamespace(
        service_id=1,
        service_name="PAC",
        company_name="Correios",
        price=Decimal("20.00"),
        delivery_time_days=5,
    )

    repository = AsyncMock()
    repository.get_by_idempotency_key.return_value = None
    repository.get_cart_for_checkout.return_value = cart
    repository.get_address_for_user.return_value = address
    repository.lock_cart_for_checkout.return_value = cart
    repository.lock_variants.return_value = [variant]
    repository.get_active_reserved_quantity.return_value = 4
    shipping_service = AsyncMock()
    shipping_service.calculate_quotes_for_products.return_value = [quote]
    session = AsyncMock()
    service = _service(repository, shipping_service, session)

    checkout_in = CheckoutConfirmSchema(
        address_id=address_id,
        shipping_service_id=1,
        expected_total_amount=Decimal("40.00"),
        payment_method=PaymentMethodEnum.PIX,
        installments=1,
    )

    with pytest.raises(ValueError, match="Estoque insuficiente"):
        await service.confirm(user_id, checkout_in, uuid4())

    session.rollback.assert_awaited_once()
    repository.create_checkout_order.assert_not_awaited()
