import logging
from decimal import Decimal
from typing import Optional, Tuple

from src.models.catalog import ProductVariant
from src.models.enums import PricingStatus

logger = logging.getLogger(__name__)


def select_unit_price(
    variant: ProductVariant, variant_quantity: int
) -> Tuple[Decimal, Optional[int]]:
    """Preço unitário pela tabela da variação (spec 008).

    Aplica a maior faixa com `min_quantity <= variant_quantity` e cobra
    `min(linha de 1 unidade, faixa)`. O snapshot de faixa é `None` quando vale a linha 1.
    A quantidade nunca é somada entre variações.
    """
    tiers = list(variant.pricing_tiers)
    line_one = next((t for t in tiers if t.min_quantity == 1), None)
    if line_one is None:
        logger.warning("variant_without_unit_price_line variant_id=%s", variant.id)
        unit_price = Decimal(variant.base_price)
    else:
        unit_price = Decimal(line_one.unit_price)
    applicable = [t for t in tiers if 2 <= t.min_quantity <= variant_quantity]
    if not applicable:
        return unit_price, None
    tier = max(applicable, key=lambda current: current.min_quantity)
    if Decimal(tier.unit_price) < unit_price:
        return Decimal(tier.unit_price), tier.min_quantity
    return unit_price, None


def is_variant_purchasable(variant: ProductVariant) -> bool:
    """Variação publicada, com preço confirmado, de produto listado na loja."""
    return bool(
        variant.is_active
        and variant.pricing_status == PricingStatus.CONFIRMED
        and variant.product.store_listed
    )
