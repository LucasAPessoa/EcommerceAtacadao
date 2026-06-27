from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.catalog.category_schema import CategoryResponseSchema
from src.models.catalog import Category

class CategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: dict) -> CategoryResponseSchema:
        """Cria uma nova categoria no banco de dados."""
        new_category = Category(**data)
        self.session.add(new_category)
        await self.session.commit()
        await self.session.refresh(new_category)
        return new_category