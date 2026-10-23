from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.category_repository import CategoryRepository
from src.schemas.catalog.category_schema import (
    CategoryResponseSchema,
)
from src.services.catalog.category_service import CategoryService


def get_category_service(
    session: DbSession,
) -> CategoryService:
    repository = CategoryRepository(session)
    return CategoryService(repository)


router = build_crud_router(
    prefix="/categories",
    tags=["Categories"],
    service_dependency=get_category_service,
    response_schema=CategoryResponseSchema,
    verbs={
        "list": "list_categories",
        "get": "get_category_by_id",
    },
    not_found_message="Categoria não encontrada.",
    supports_pagination=True,
    read_only=True,
)
