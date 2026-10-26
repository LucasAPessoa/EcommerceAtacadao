from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.product_listing_repository import ProductListingRepository
from src.schemas.catalog.product_listing_schema import (
    ProductListingResponseSchema,
)
from src.services.catalog.product_listing_service import ProductListingService


def get_product_listing_service(
    session: DbSession,
) -> ProductListingService:
    repository = ProductListingRepository(session)
    return ProductListingService(repository)


router = build_crud_router(
    prefix="/product-listings",
    tags=["Product Listings"],
    service_dependency=get_product_listing_service,
    response_schema=ProductListingResponseSchema,
    verbs={
        "list": "list_listings",
        "get": "get_listing_by_id",
    },
    not_found_message="Anúncio (listing) não encontrado.",
    read_only=True,
)
