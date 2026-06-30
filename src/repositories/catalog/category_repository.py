from sqlalchemy import select
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
    
    async def list(self) -> list[CategoryResponseSchema]:
        """Lista todas as categorias no banco de dados."""
        stmt = select(Category)
        return (await self.session.scalars(stmt)).all()

    async def get_by_id(self, category_id: int) -> CategoryResponseSchema:
        """Obtém uma categoria pelo seu ID."""
        return await self.session.get(Category, category_id)
    
    async def update(self, category_id: int, data: dict) -> CategoryResponseSchema:
        """Atualiza uma categoria existente no banco de dados."""
        category = await self.session.get(Category, category_id)

        if not category:
            return None
        
        for key, value in data.items():
            setattr(category, key, value)

        await self.session.commit()
        await self.session.refresh(category)
        
        return category
