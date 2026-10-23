from uuid import UUID

from src.repositories.catalog.category_repository import CategoryRepository
from src.schemas.catalog.category_schema import (
    CategoryResponseSchema,
)


class CategoryService:
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    async def list_categories(
        self, skip: int = 0, limit: int = 100
    ) -> list[CategoryResponseSchema]:
        categories = await self.repository.get_all(skip=skip, limit=limit)
        return [CategoryResponseSchema.model_validate(category) for category in categories]

    async def get_category_by_id(self, category_id: UUID) -> CategoryResponseSchema | None:
        category = await self.repository.get_by_id(category_id)
        if not category:
            return None
        return CategoryResponseSchema.model_validate(category)
