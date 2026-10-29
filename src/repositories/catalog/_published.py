"""Regra SQL de variação publicada (spec 008), espelho de ``is_variant_published``."""

from typing import Any

from sqlalchemy import and_, exists
from sqlalchemy.sql.elements import ColumnElement

from src.models.catalog import PricingTier, Product, ProductVariant
from src.models.enums import PricingStatus


def has_unit_price_line(variant: Any = ProductVariant) -> ColumnElement[bool]:
    return exists().where(PricingTier.variant_id == variant.id, PricingTier.min_quantity == 1)


def published(variant: Any = ProductVariant, product: Any = Product) -> ColumnElement[bool]:
    """Variação ativa, não excluída, de produto listado, com a linha de 1 unidade."""
    return and_(
        variant.is_active.is_(True),
        variant.deleted_at.is_(None),
        product.store_listed.is_(True),
        has_unit_price_line(variant),
    )


def purchasable(variant: Any = ProductVariant, product: Any = Product) -> ColumnElement[bool]:
    """Publicada e com preço confirmado: o que a loja pública pode mostrar."""
    return and_(published(variant, product), variant.pricing_status == PricingStatus.CONFIRMED)
