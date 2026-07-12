from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.listing_attribute_schema import (
    ListingAttributeCreateSchema, ListingAttributeUpdateSchema, ListingAttributeResponseSchema,
)
from src.repositories.catalog.listing_attribute_repository import ListingAttributeRepository
from src.services.catalog.listing_attribute_service import ListingAttributeService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_listing_attribute_service(session: AsyncSession = Depends(get_db)) -> ListingAttributeService:
    repository = ListingAttributeRepository(session)
    return ListingAttributeService(repository)


router = build_crud_router(
    prefix="/listing-attributes",
    tags=["Listing Attributes"],
    service_dependency=get_listing_attribute_service,
    create_schema=ListingAttributeCreateSchema,
    update_schema=ListingAttributeUpdateSchema,
    response_schema=ListingAttributeResponseSchema,
    verbs={
        "create": "create_attribute",
        "list": "list_attributes",
        "get": "get_attribute_by_id",
        "update": "update_attribute",
        "delete": "delete_attribute",
    },
    not_found_message="Atributo do anúncio não encontrado.",
    write_roles=["admin"],
)
