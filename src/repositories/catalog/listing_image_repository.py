from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ListingImage
from src.schemas.catalog.listing_image_schema import ListingImageResponseSchema

class ListingImageRepository(BaseRepository[ListingImage, ListingImageResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ListingImage, 
            response_schema=ListingImageResponseSchema, 
            session=session
        )