from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ProductQuestion
from src.schemas.catalog.product_question_schema import ProductQuestionResponseSchema

class ProductQuestionRepository(BaseRepository[ProductQuestion, ProductQuestionResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductQuestion, 
            response_schema=ProductQuestionResponseSchema, 
            session=session
        )