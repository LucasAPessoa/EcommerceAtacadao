from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.product_image_schema import (
    ProductImageCreateSchema, ProductImageUpdateSchema, ProductImageResponseSchema,
)
from src.repositories.catalog.product_image_repository import ProductImageRepository
from src.services.catalog.product_image_service import ProductImageService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_product_image_service(session: AsyncSession = Depends(get_db)) -> ProductImageService:
    repository = ProductImageRepository(session)
    return ProductImageService(repository)


router = build_crud_router(
    prefix="/product-images",
    tags=["Product Images"],
    service_dependency=get_product_image_service,
    create_schema=ProductImageCreateSchema,
    update_schema=ProductImageUpdateSchema,
    response_schema=ProductImageResponseSchema,
    verbs={
        "create": "create_image",
        "list": "list_images",
        "get": "get_image_by_id",
        "update": "update_image",
        "delete": "delete_image",
    },
    not_found_message="Imagem do produto não encontrada.",
    write_roles=["admin"],
)
