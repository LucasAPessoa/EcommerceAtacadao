from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.product_review_repository import ProductReviewRepository
from src.schemas.catalog.product_review_schema import (
    ProductReviewCreateSchema,
    ProductReviewResponseSchema,
    ProductReviewUpdateSchema,
)
from src.services.catalog.product_review_service import ProductReviewService


def get_product_review_service(
    session: DbSession,
) -> ProductReviewService:
    repository = ProductReviewRepository(session)
    return ProductReviewService(repository)


# Criar avaliação: qualquer cliente autenticado pode.
# Atualizar/excluir: moderação, restrita a admin (não há verificação de dono da
# avaliação implementada no service, então permitir o próprio cliente editar
# livremente ainda exigiria essa checagem extra antes de liberar).
router = build_crud_router(
    prefix="/product-reviews",
    tags=["Product Reviews"],
    service_dependency=get_product_review_service,
    create_schema=ProductReviewCreateSchema,
    update_schema=ProductReviewUpdateSchema,
    response_schema=ProductReviewResponseSchema,
    verbs={
        "create": "create_review",
        "list": "list_reviews",
        "get": "get_review_by_id",
        "update": "update_review",
        "delete": "delete_review",
    },
    not_found_message="Avaliação não encontrada.",
    write_roles=["admin"],
    create_as_author=True,
    hide_unapproved_from_public=True,
)
