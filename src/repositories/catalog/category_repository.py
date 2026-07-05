from sqlalchemy.ext.asyncio import AsyncSession
from src.models.catalog import Category
from src.repositories.base_repository import BaseRepository

class CategoryRepository(BaseRepository[Category]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Category, session=session)