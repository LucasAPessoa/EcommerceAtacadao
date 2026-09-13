from decimal import Decimal
from typing import Optional, Tuple

from src.models.catalog import ProductVariant


def select_unit_price(
    variant: ProductVariant, product_quantity: int
) -> Tuple[Decimal, Optional[int]]:
    """Aplica a maior faixa atacadista elegível à quantidade consolidada do produto."""
    applicable = [
        tier for tier in variant.product.pricing_tiers if tier.min_quantity <= product_quantity
    ]
    if not applicable:
        return Decimal(variant.base_price), None
    tier = max(applicable, key=lambda current: current.min_quantity)
    return Decimal(tier.unit_price), tier.min_quantity
