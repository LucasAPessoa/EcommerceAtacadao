from sqlalchemy.ext.asyncio import AsyncSession
from src.models.catalog import Category
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.category_schema import CategoryResponseSchema

class CategoryRepository(BaseRepository[Category, CategoryResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Category, session=session, response_schema=CategoryResponseSchema)