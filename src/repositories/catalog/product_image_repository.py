from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ProductImage
from src.schemas.catalog.product_image_schema import ProductImageResponseSchema

class ProductImageRepository(BaseRepository[ProductImage, ProductImageResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductImage, 
            response_schema=ProductImageResponseSchema, 
            session=session
        )