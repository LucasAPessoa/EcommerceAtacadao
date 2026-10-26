"""Expressões SQL reutilizáveis do portal admin (007: data-model "Valores derivados").

Tudo é derivado dos dados atuais, sem persistência: nome efetivo, estoque, faixa de preço,
motivo de pendência (R5) e "personalizado".
"""

from typing import Any

from sqlalchemy import Select, and_, case, false, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
from src.models.catalog import Product, ProductVariant
from src.models.catalog_presentation import ProductSitePresentation


def effective_name() -> ColumnElement[str]:
    """``COALESCE(presentation.name, products.name)`` (exige o join com a apresentação)."""
    return func.coalesce(ProductSitePresentation.name, Product.name)


def variant_pending_reason(
    variant: Any = ProductVariant, product: Any = Product
) -> ColumnElement[str | None]:
    """Motivo de pendência da variação (R5), ou NULL.

    Só vale para variação inativa e não excluída de produto não excluído. O primeiro
    motivo que se aplicar, na ordem da sync: peso, medidas, preço.
    """
    bad_dimension = or_(
        variant.width_cm.is_(None),
        variant.width_cm <= 0,
        variant.height_cm.is_(None),
        variant.height_cm <= 0,
        variant.length_cm.is_(None),
        variant.length_cm <= 0,
    )
    return case(
        (
            and_(
                variant.is_active.is_(False),
                variant.deleted_at.is_(None),
                product.deleted_at.is_(None),
            ),
            case(
                (or_(variant.weight_kg.is_(None), variant.weight_kg <= 0), INCOMPLETE_WEIGHT),
                (bad_dimension, INCOMPLETE_DIMENSIONS),
                (variant.base_price <= 0, INCOMPLETE_PRICE),
                else_=None,
            ),
        ),
        else_=None,
    )


def customized() -> ColumnElement[bool]:
    """Apresentação com algum texto não NULL ou categorias travadas (exige o join)."""
    return func.coalesce(
        or_(
            ProductSitePresentation.name.is_not(None),
            ProductSitePresentation.description.is_not(None),
            ProductSitePresentation.complementary_description.is_not(None),
            ProductSitePresentation.categories_locked.is_(True),
        ),
        false(),
    )


def variant_aggregates() -> Any:
    """Subconsulta por produto: estoque, menor/maior preço (variações ativas) e pendências.

    Agrega uma vez por produto (hash aggregate) em vez de subconsultas correlacionadas, para
    ordenar e filtrar milhares de produtos sem varrer as variações por linha.
    """
    selling = and_(ProductVariant.is_active.is_(True), ProductVariant.deleted_at.is_(None))
    reason = variant_pending_reason()
    return (
        select(
            ProductVariant.product_id.label("product_id"),
            func.coalesce(func.sum(case((selling, ProductVariant.stock_quantity), else_=0)), 0)
            .cast(ProductVariant.stock_quantity.type)
            .label("stock"),
            func.min(case((selling, ProductVariant.base_price), else_=None)).label("min_price"),
            func.max(case((selling, ProductVariant.base_price), else_=None)).label("max_price"),
            func.count(case((reason.is_not(None), literal(1)), else_=None)).label("pending_count"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
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
