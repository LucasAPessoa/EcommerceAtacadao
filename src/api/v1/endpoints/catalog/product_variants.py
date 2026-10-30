from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.catalog.product_variant_schema import ProductVariantPublicSchema
from src.services.catalog.product_variant_service import ProductVariantService


def get_product_variant_service(
    session: DbSession,
) -> ProductVariantService:
    repository = ProductVariantRepository(session)
    return ProductVariantService(repository)


router = build_crud_router(
    prefix="/product-variants",
    tags=["Product Variants"],
    service_dependency=get_product_variant_service,
    response_schema=ProductVariantPublicSchema,
    verbs={
        "list": "list_variants",
        "get": "get_variant_by_id",
    },
    not_found_message="Variação do produto não encontrada.",
    read_only=True,
    list_filters={"product_id": "Filtra pelo produto (UUID)."},
)
