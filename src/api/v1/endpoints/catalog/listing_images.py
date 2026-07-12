from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.listing_image_schema import (
    ListingImageCreateSchema, ListingImageUpdateSchema, ListingImageResponseSchema,
)
from src.repositories.catalog.listing_image_repository import ListingImageRepository
from src.services.catalog.listing_image_service import ListingImageService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_listing_image_service(session: AsyncSession = Depends(get_db)) -> ListingImageService:
    repository = ListingImageRepository(session)
    return ListingImageService(repository)


router = build_crud_router(
    prefix="/listing-images",
    tags=["Listing Images"],
    service_dependency=get_listing_image_service,
    create_schema=ListingImageCreateSchema,
    update_schema=ListingImageUpdateSchema,
    response_schema=ListingImageResponseSchema,
    verbs={
        "create": "create_image",
        "list": "list_images",
        "get": "get_image_by_id",
        "update": "update_image",
        "delete": "delete_image",
    },
    not_found_message="Imagem do anúncio não encontrada, che.",
    write_roles=["admin"],
)
