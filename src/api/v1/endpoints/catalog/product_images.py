from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.product_image_repository import ProductImageRepository
from src.schemas.catalog.product_image_schema import (
    ProductImageResponseSchema,
)
from src.services.catalog.product_image_service import ProductImageService


def get_product_image_service(
    session: DbSession,
) -> ProductImageService:
    repository = ProductImageRepository(session)
    return ProductImageService(repository)


router = build_crud_router(
    prefix="/product-images",
    tags=["Product Images"],
    service_dependency=get_product_image_service,
    response_schema=ProductImageResponseSchema,
    verbs={
        "list": "list_images",
        "get": "get_image_by_id",
    },
    not_found_message="Imagem do produto não encontrada.",
    read_only=True,
    list_filters={
        "product_id": "Filtra pelo produto (UUID).",
        "variant_id": "Filtra pela variação (UUID).",
    },
)
