from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import ProductReview
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.product_review_schema import ProductReviewResponseSchema


class ProductReviewRepository(BaseRepository[ProductReview, ProductReviewResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductReview, response_schema=ProductReviewResponseSchema, session=session
        )

    async def get_all(
        self, skip: int = 0, limit: int = 100, only_approved: bool = False
    ) -> List[ProductReviewResponseSchema]:
        query = select(ProductReview)
        if only_approved:
            query = query.where(ProductReview.is_approved.is_(True))
        result = await self.session.execute(query.offset(skip).limit(limit))
        return [self.response_schema.model_validate(o) for o in result.scalars().all()]

    async def get_by_id(
        self, id: UUID, only_approved: bool = False
    ) -> Optional[ProductReviewResponseSchema]:
        query = select(ProductReview).where(ProductReview.id == id)
        if only_approved:
            query = query.where(ProductReview.is_approved.is_(True))
        obj = (await self.session.execute(query)).scalar_one_or_none()
        return self.response_schema.model_validate(obj) if obj else None
