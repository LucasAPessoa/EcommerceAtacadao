from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import PaymentMethodEnum
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
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
