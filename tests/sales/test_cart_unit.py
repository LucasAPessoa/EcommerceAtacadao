from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from src.services.sales.cart_service import CartService


def _variant(product_id, sku: str):
    now = datetime.now(UTC).replace(tzinfo=None)
    product = SimpleNamespace(
        id=product_id,
        pricing_tiers=[
            SimpleNamespace(min_quantity=5, unit_price=Decimal("8.50")),
            SimpleNamespace(min_quantity=10, unit_price=Decimal("7.25")),
        ],
    )
    return SimpleNamespace(
        id=uuid4(),
        product_id=product_id,
        product=product,
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


def test_cart_total_uses_highest_tier_for_consolidated_product_quantity() -> None:
    product_id = uuid4()
    first_variant = _variant(product_id, "SKU-A")
    second_variant = _variant(product_id, "SKU-B")
    now = datetime.now(UTC).replace(tzinfo=None)
    cart = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        created_at=now,
        updated_at=now,
        items=[
            SimpleNamespace(
                id=uuid4(), variant_id=first_variant.id, variant=first_variant, quantity=5
            ),
            SimpleNamespace(
                id=uuid4(), variant_id=second_variant.id, variant=second_variant, quantity=5
            ),
        ],
    )

    response = CartService._response(cart)

    assert [item.unit_price for item in response.items] == [Decimal("7.25"), Decimal("7.25")]
    assert response.total_amount == Decimal("72.50")
