import uuid
import warnings

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SAWarning
from sqlalchemy.sql.compiler import COLLECT_CARTESIAN_PRODUCTS, WARN_LINTING

from src.models.catalog import Category, Product
from src.models.catalog_presentation import ProductSitePresentation
from src.repositories.catalog.product_repository import ProductRepository

LINTING = COLLECT_CARTESIAN_PRODUCTS | WARN_LINTING


def test_category_filter_has_no_cartesian_product() -> None:
    stmt = (
        select(Product.id)
        .outerjoin(ProductSitePresentation, ProductSitePresentation.product_id == Product.id)
        .where(ProductRepository._effective_category_exists(uuid.uuid4()))
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        sql = str(stmt.compile(dialect=postgresql.dialect(), linting=LINTING))
    # Cada EXISTS correlaciona Category pela tabela de vínculo (sem FROM solto).
    assert "categories.id = product_site_categories.category_id" in sql
    assert "categories.id = product_category.category_id" in sql


def test_linting_detects_cartesian_product() -> None:
    """Anti-falso-positivo: o linting usado acima dispara de fato."""
    stmt = select(Product.id).where(Category.id == uuid.uuid4())
    with pytest.warns(SAWarning, match="cartesian"):
        stmt.compile(dialect=postgresql.dialect(), linting=LINTING)
