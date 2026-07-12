from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.product_variant_schema import (
    ProductVariantCreateSchema, ProductVariantUpdateSchema, ProductVariantResponseSchema,
)
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.services.catalog.product_variant_service import ProductVariantService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_product_variant_service(session: AsyncSession = Depends(get_db)) -> ProductVariantService:
    repository = ProductVariantRepository(session)
    return ProductVariantService(repository)


router = build_crud_router(
    prefix="/product-variants",
    tags=["Product Variants"],
    service_dependency=get_product_variant_service,
    create_schema=ProductVariantCreateSchema,
    update_schema=ProductVariantUpdateSchema,
    response_schema=ProductVariantResponseSchema,
    verbs={
        "create": "create_variant",
        "list": "list_variants",
        "get": "get_variant_by_id",
        "update": "update_variant",
        "delete": "delete_variant",
    },
    not_found_message="Variação do produto não encontrada.",
    write_roles=["admin"],
)
