from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.product_listing_schema import (
    ProductListingCreateSchema, ProductListingUpdateSchema, ProductListingResponseSchema,
)
from src.repositories.catalog.product_listing_repository import ProductListingRepository
from src.services.catalog.product_listing_service import ProductListingService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_product_listing_service(session: AsyncSession = Depends(get_db)) -> ProductListingService:
    repository = ProductListingRepository(session)
    return ProductListingService(repository)


router = build_crud_router(
    prefix="/product-listings",
    tags=["Product Listings"],
    service_dependency=get_product_listing_service,
    create_schema=ProductListingCreateSchema,
    update_schema=ProductListingUpdateSchema,
    response_schema=ProductListingResponseSchema,
    verbs={
        "create": "create_listing",
        "list": "list_listings",
        "get": "get_listing_by_id",
        "update": "update_listing",
        "delete": "delete_listing",
    },
    not_found_message="Anúncio (listing) não encontrado.",
    write_roles=["admin"],
)
