from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import Product
from src.schemas.catalog.product_schema import ProductResponseSchema

class ProductRepository(BaseRepository[Product, ProductResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=Product, 
            response_schema=ProductResponseSchema, 
            session=session
        )