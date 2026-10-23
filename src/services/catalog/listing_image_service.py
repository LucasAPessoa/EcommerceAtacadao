from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.listing_image_repository import ListingImageRepository
from src.schemas.catalog.listing_image_schema import (
    ListingImageResponseSchema,
)


class ListingImageService:
    def __init__(self, repository: ListingImageRepository):
        self.repository = repository

    async def list_images(self) -> List[ListingImageResponseSchema]:
        return await self.repository.get_all()

    async def get_image_by_id(self, image_id: UUID) -> Optional[ListingImageResponseSchema]:
        return await self.repository.get_by_id(image_id)
