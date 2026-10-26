from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.listing_attribute_repository import ListingAttributeRepository
from src.schemas.catalog.listing_attribute_schema import (
    ListingAttributeResponseSchema,
)


class ListingAttributeService:
    def __init__(self, repository: ListingAttributeRepository):
        self.repository = repository

    async def list_attributes(self) -> List[ListingAttributeResponseSchema]:
        return await self.repository.get_all()

    async def get_attribute_by_id(
        self, attribute_id: UUID
    ) -> Optional[ListingAttributeResponseSchema]:
        return await self.repository.get_by_id(attribute_id)
