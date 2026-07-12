from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ProductListing
from src.schemas.catalog.product_listing_schema import ProductListingResponseSchema

class ProductListingRepository(BaseRepository[ProductListing, ProductListingResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductListing, 
            response_schema=ProductListingResponseSchema, 
            session=session
        )