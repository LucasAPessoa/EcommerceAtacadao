from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.category_schema import CategoryCreateSchema, CategoryUpdateSchema, CategoryResponseSchema
from src.repositories.catalog.category_repository import CategoryRepository
from src.services.catalog.category_service import CategoryService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_category_service(session: AsyncSession = Depends(get_db)) -> CategoryService:
    repository = CategoryRepository(session)
    return CategoryService(repository)


router = build_crud_router(
    prefix="/categories",
    tags=["Categories"],
    service_dependency=get_category_service,
    create_schema=CategoryCreateSchema,
    update_schema=CategoryUpdateSchema,
    response_schema=CategoryResponseSchema,
    verbs={
        "create": "create_category",
        "list": "list_categories",
        "get": "get_category_by_id",
        "update": "update_category",
        "delete": "delete_category",
    },
    not_found_message="Categoria não encontrada.",
    write_roles=["admin"],
)
