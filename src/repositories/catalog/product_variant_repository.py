from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ProductVariant
from src.schemas.catalog.product_variant_schema import ProductVariantResponseSchema

class ProductVariantRepository(BaseRepository[ProductVariant, ProductVariantResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductVariant, 
            response_schema=ProductVariantResponseSchema, 
            session=session
        )