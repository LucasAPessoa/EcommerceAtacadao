from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_image_repository import ProductImageRepository
from src.schemas.catalog.product_image_schema import (
    ProductImageResponseSchema,
)


class ProductImageService:
    def __init__(self, repository: ProductImageRepository):
        self.repository = repository

    async def list_images(
        self, product_id: Optional[UUID] = None, variant_id: Optional[UUID] = None
    ) -> List[ProductImageResponseSchema]:
        if product_id is None and variant_id is None:
            return await self.repository.get_all()
        return await self.repository.get_filtered(product_id=product_id, variant_id=variant_id)

    async def get_image_by_id(self, image_id: UUID) -> Optional[ProductImageResponseSchema]:
        return await self.repository.get_by_id(image_id)
