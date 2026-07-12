from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import ListingAttribute
from src.schemas.catalog.listing_attribute_schema import ListingAttributeResponseSchema

class ListingAttributeRepository(BaseRepository[ListingAttribute, ListingAttributeResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ListingAttribute, 
            response_schema=ListingAttributeResponseSchema, 
            session=session
        )