from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.listing_image_repository import ListingImageRepository
from src.schemas.catalog.listing_image_schema import (
    ListingImageResponseSchema,
)
from src.services.catalog.listing_image_service import ListingImageService


def get_listing_image_service(
    session: DbSession,
) -> ListingImageService:
    repository = ListingImageRepository(session)
    return ListingImageService(repository)


router = build_crud_router(
    prefix="/listing-images",
    tags=["Listing Images"],
    service_dependency=get_listing_image_service,
    response_schema=ListingImageResponseSchema,
    verbs={
        "list": "list_images",
        "get": "get_image_by_id",
    },
    not_found_message="Imagem do anúncio não encontrada, che.",
    read_only=True,
)
