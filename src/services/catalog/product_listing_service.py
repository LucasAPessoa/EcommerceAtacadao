from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_listing_repository import ProductListingRepository
from src.schemas.catalog.product_listing_schema import (
    ProductListingResponseSchema,
)


class ProductListingService:
    def __init__(self, repository: ProductListingRepository):
        self.repository = repository

    async def list_listings(self) -> List[ProductListingResponseSchema]:
        return await self.repository.get_all()

    async def get_listing_by_id(self, listing_id: UUID) -> Optional[ProductListingResponseSchema]:
        return await self.repository.get_by_id(listing_id)
