from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.listing_attribute_repository import ListingAttributeRepository
from src.schemas.catalog.listing_attribute_schema import (
    ListingAttributeCreateSchema,
    ListingAttributeResponseSchema,
    ListingAttributeUpdateSchema,
)
from src.services.catalog.listing_attribute_service import ListingAttributeService


def get_listing_attribute_service(
    session: DbSession,
) -> ListingAttributeService:
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
    create_roles=["admin"],
    write_roles=["admin"],
)
