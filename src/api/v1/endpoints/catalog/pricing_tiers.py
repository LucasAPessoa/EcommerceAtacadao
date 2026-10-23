from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.pricing_tier_repository import PricingTierRepository
from src.schemas.catalog.pricing_tier_schema import (
    PricingTierCreateSchema,
    PricingTierResponseSchema,
    PricingTierUpdateSchema,
)
from src.services.catalog.pricing_tier_service import PricingTierService


def get_tier_service(
    session: DbSession,
) -> PricingTierService:
    repository = PricingTierRepository(session)
    return PricingTierService(repository)


router = build_crud_router(
    prefix="/pricing-tiers",
    tags=["Pricing Tiers"],
    service_dependency=get_tier_service,
    create_schema=PricingTierCreateSchema,
    update_schema=PricingTierUpdateSchema,
    response_schema=PricingTierResponseSchema,
    verbs={
        "create": "create_tier",
        "list": "list_tiers",
        "get": "get_tier_by_id",
        "update": "update_tier",
        "delete": "delete_tier",
    },
    not_found_message="Tier não encontrado.",
    create_roles=["admin"],
    write_roles=["admin"],
    list_filters={"product_id": "Filtra pelo produto (UUID)."},
)
