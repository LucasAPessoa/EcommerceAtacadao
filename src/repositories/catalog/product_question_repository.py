from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import ProductQuestion
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.product_question_schema import ProductQuestionResponseSchema


class ProductQuestionRepository(BaseRepository[ProductQuestion, ProductQuestionResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductQuestion, response_schema=ProductQuestionResponseSchema, session=session
        )

    async def get_by_product(self, product_id: UUID) -> List[ProductQuestionResponseSchema]:
        query = select(ProductQuestion).where(ProductQuestion.product_id == product_id)
        result = await self.session.execute(
            query.order_by(ProductQuestion.created_at, ProductQuestion.id)
        )
        return [self.response_schema.model_validate(o) for o in result.scalars().all()]
