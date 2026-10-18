from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import get_db
from src.repositories.catalog.product_image_repository import ProductImageRepository
from src.schemas.catalog.product_image_schema import (
    ProductImageCreateSchema,
    ProductImageResponseSchema,
    ProductImageUpdateSchema,
)
from src.services.catalog.product_image_service import ProductImageService


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
    create_roles=["admin"],
    write_roles=["admin"],
)
