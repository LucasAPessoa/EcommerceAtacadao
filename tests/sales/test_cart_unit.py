from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import PricingStatus
from src.services.sales.cart_service import CartService


def _variant(product_id, sku: str, tiers=((1, "10.00"), (5, "8.50"), (10, "7.25"))):
    now = datetime.now(UTC).replace(tzinfo=None)
    product = SimpleNamespace(
        id=product_id,
        is_active=True,
        deleted_at=None,
        store_listed=True,
    )
    return SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        product=product,
        pricing_status=PricingStatus.CONFIRMED,
        pricing_tiers=[SimpleNamespace(min_quantity=q, unit_price=Decimal(p)) for q, p in tiers],
        bling_id=None,
        bling_sku=sku,
        variation_name=sku,
        gtin=None,
        packaging_gtin=None,
        base_price=Decimal("10.00"),
        stock_quantity=20,
        last_bling_sync=None,
        is_active=True,
        weight_kg=1.0,
        height_cm=10.0,
        width_cm=10.0,
        length_cm=10.0,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _cart(*pairs):
    now = datetime.now(UTC).replace(tzinfo=None)
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        created_at=now,
        updated_at=now,
        items=[
            SimpleNamespace(id=uuid4(), variant_id=v.id, variant=v, quantity=q) for v, q in pairs
        ],
    )


def test_cart_charges_full_price_for_variant_without_tiers() -> None:
    variant = _variant(uuid4(), "SKU-A", tiers=((1, "10.00"),))

    response = CartService._response(_cart((variant, 10)))

    assert [item.unit_price for item in response.items] == [Decimal("10.00")]
    assert response.total_amount == Decimal("100.00")


def test_cart_charges_tier_for_variant_quantity() -> None:
    variant = _variant(uuid4(), "SKU-A")

    response = CartService._response(_cart((variant, 10)))

    assert [item.unit_price for item in response.items] == [Decimal("7.25")]
    assert response.total_amount == Decimal("72.50")


def test_cart_does_not_sum_quantities_across_variants() -> None:
    product_id = uuid4()
    first = _variant(product_id, "SKU-A")
    second = _variant(product_id, "SKU-B")

    response = CartService._response(_cart((first, 5), (second, 5)))

    assert [item.unit_price for item in response.items] == [Decimal("8.50"), Decimal("8.50")]


def test_cart_tier_not_below_line_one_charges_line_one() -> None:
    variant = _variant(uuid4(), "SKU-A", tiers=((1, "6.00"), (10, "7.25")))

    response = CartService._response(_cart((variant, 10)))

    assert [item.unit_price for item in response.items] == [Decimal("6.00")]


@pytest.mark.parametrize("target", ["unconfirmed", "unpublished", "unlisted"])
async def test_add_item_rejects_unavailable_variation(target: str) -> None:
    variant = _variant(uuid4(), "SKU-A")
    if target == "unconfirmed":
        variant.pricing_status = PricingStatus.PENDING
    elif target == "unpublished":
        variant.is_active = False
    else:
        variant.product.store_listed = False
    variants = SimpleNamespace(get_for_sale=AsyncMock(return_value=variant))
    service = CartService(
        repository=AsyncMock(), variant_repository=variants, stock_repository=AsyncMock()
    )

    with pytest.raises(ValueError, match="não está disponível"):
        await service.add_item(uuid4(), SimpleNamespace(variant_id=variant.id, quantity=1))
