"""Expressões SQL reutilizáveis do portal admin (007: data-model "Valores derivados").

Tudo é derivado dos dados atuais, sem persistência: estoque, faixa de preço, motivo de
pendência (R5), variação publicada e avisos de preço (spec 008).
"""

from typing import Any

from sqlalchemy import Select, and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
from src.models.catalog import PricingTier, Product, ProductVariant
from src.models.enums import PriceSource, PricingStatus
from src.repositories.catalog._published import published

PRICE_NOT_SET = "PRICE_NOT_SET"
STORE_PRICE_MISSING = "STORE_PRICE_MISSING"
TIER_NOT_BELOW_UNIT = "TIER_NOT_BELOW_UNIT"


def _alive(variant: Any, product: Any) -> ColumnElement[bool]:
    """Variação e produto não excluídos (os avisos nunca valem para excluídos)."""
    return and_(variant.deleted_at.is_(None), product.deleted_at.is_(None))


def tier_stats() -> Any:
    """Por variação: preço da linha de 1 unidade e maior preço das faixas a partir de 2.

    Um único hash aggregate sobre as faixas; o agregado por produto junta isto em vez de
    rodar EXISTS correlacionados por variação (que o planner pode reexecutar por produto).
    """
    return (
        select(
            PricingTier.variant_id.label("variant_id"),
            func.max(case((PricingTier.min_quantity == 1, PricingTier.unit_price))).label(
                "unit_line"
            ),
            func.max(case((PricingTier.min_quantity > 1, PricingTier.unit_price))).label(
                "max_tier"
            ),
        )
        .where(PricingTier.variant_id.is_not(None))
        .group_by(PricingTier.variant_id)
        .subquery("tier_stats")
    )


def _has_line(tiers: Any) -> Any:
    return None if tiers is None else tiers.c.unit_line.is_not(None)


def tier_not_below_unit(
    variant: Any = ProductVariant, product: Any = Product, tiers: Any = None
) -> ColumnElement[bool]:
    """Alguma faixa (a partir de 2) com preço >= ao da linha de 1 unidade (não excluídos).

    Com ``tiers`` (de :func:`tier_stats`, já juntado), compara as colunas em vez do EXISTS.
    """
    if tiers is not None:
        return and_(
            _alive(variant, product),
            func.coalesce(tiers.c.max_tier >= tiers.c.unit_line, False),
        )
    line_one = aliased(PricingTier)
    tier = aliased(PricingTier)
    return exists().where(
        _alive(variant, product),
        line_one.variant_id == variant.id,
        line_one.min_quantity == 1,
        tier.variant_id == variant.id,
        tier.min_quantity > 1,
        tier.unit_price >= line_one.unit_price,
    )


def store_price_missing(
    variant: Any = ProductVariant, product: Any = Product, tiers: Any = None
) -> Any:
    """Variação publicada que usa o preço geral do Bling (vínculo sem preço)."""
    return and_(
        _alive(variant, product),
        published(variant, product, _has_line(tiers)),
        variant.price_source == PriceSource.GENERAL,
    )


def price_not_set(variant: Any = ProductVariant, product: Any = Product) -> Any:
    """Variação de produto listado, preço geral e sem preço no Bling."""
    return and_(
        _alive(variant, product),
        product.store_listed.is_(True),
        variant.price_source == PriceSource.GENERAL,
        variant.base_price <= 0,
    )


def pricing_pending(
    variant: Any = ProductVariant, product: Any = Product, tiers: Any = None
) -> Any:
    return and_(
        _alive(variant, product),
        published(variant, product, _has_line(tiers)),
        variant.pricing_status == PricingStatus.PENDING,
    )


def variant_pending_reason(
    variant: Any = ProductVariant, product: Any = Product, tiers: Any = None
) -> ColumnElement[str | None]:
    """Motivo de pendência da variação (R5), ou NULL.

    Só vale para variação não excluída de produto não excluído. O primeiro motivo que se
    aplicar: para variação inativa, na ordem da sync, peso, medidas, preço; depois os avisos de
    preço (FR-011): preço não definido, preço da loja ausente, faixa não abaixo de 1 unidade.
    """
    bad_dimension = or_(
        variant.width_cm.is_(None),
        variant.width_cm <= 0,
        variant.height_cm.is_(None),
        variant.height_cm <= 0,
        variant.length_cm.is_(None),
        variant.length_cm <= 0,
    )
    incomplete = case(
        (
            and_(variant.is_active.is_(False), _alive(variant, product)),
            case(
                (or_(variant.weight_kg.is_(None), variant.weight_kg <= 0), INCOMPLETE_WEIGHT),
                (bad_dimension, INCOMPLETE_DIMENSIONS),
                (variant.base_price <= 0, INCOMPLETE_PRICE),
                else_=None,
            ),
        ),
        else_=None,
    )
    warning = case(
        (price_not_set(variant, product), PRICE_NOT_SET),
        (store_price_missing(variant, product, tiers), STORE_PRICE_MISSING),
        (tier_not_below_unit(variant, product, tiers), TIER_NOT_BELOW_UNIT),
        else_=None,
    )
    return func.coalesce(incomplete, warning)


def variant_aggregates() -> Any:
    """Subconsulta por produto: estoque, menor/maior preço (variações ativas) e pendências.

    Agrega uma vez por produto (hash aggregate) em vez de subconsultas correlacionadas, para
    ordenar e filtrar milhares de produtos sem varrer as variações por linha.
    """
    selling = and_(ProductVariant.is_active.is_(True), ProductVariant.deleted_at.is_(None))
    tiers = tier_stats()
    reason = variant_pending_reason(tiers=tiers)
    return (
        select(
            ProductVariant.product_id.label("product_id"),
            func.coalesce(func.sum(case((selling, ProductVariant.stock_quantity), else_=0)), 0)
            .cast(ProductVariant.stock_quantity.type)
            .label("stock"),
            func.min(case((selling, ProductVariant.base_price), else_=None)).label("min_price"),
            func.max(case((selling, ProductVariant.base_price), else_=None)).label("max_price"),
            func.count(case((reason.is_not(None), literal(1)), else_=None)).label("pending_count"),
            func.count(case((pricing_pending(tiers=tiers), literal(1)), else_=None)).label(
                "pricing_pending"
            ),
            func.count(case((tier_not_below_unit(tiers=tiers), literal(1)), else_=None)).label(
                "tier_warning"
            ),
            func.count(case((store_price_missing(tiers=tiers), literal(1)), else_=None)).label(
                "store_price_missing"
            ),
            func.count(case((price_not_set(), literal(1)), else_=None)).label("price_not_set"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(tiers, tiers.c.variant_id == ProductVariant.id)
        .group_by(ProductVariant.product_id)
        .subquery("variant_agg")
    )


def with_aggregates(stmt: Select[Any], agg: Any) -> Select[Any]:
    """Junta os agregados ao produto (produto sem variação: estoque 0, sem preço)."""
    return stmt.outerjoin(agg, agg.c.product_id == Product.id)


def stock_of(agg: Any) -> ColumnElement[int]:
    return func.coalesce(agg.c.stock, 0)


def pending_count_of(agg: Any) -> ColumnElement[int]:
    return func.coalesce(agg.c.pending_count, 0)


def count_of(agg: Any, column: str) -> ColumnElement[int]:
    """Contador por produto do agregado (``pricing_pending``, ``tier_warning``, ...)."""
    return func.coalesce(agg.c[column], 0)
