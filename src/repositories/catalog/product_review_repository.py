from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ProductReview
from src.schemas.catalog.product_review_schema import ProductReviewResponseSchema

class ProductReviewRepository(BaseRepository[ProductReview, ProductReviewResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductReview, 
            response_schema=ProductReviewResponseSchema, 
            session=session
        )