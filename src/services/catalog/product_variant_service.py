from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.catalog.product_variant_schema import ProductVariantPublicSchema


class ProductVariantService:
    def __init__(self, repository: ProductVariantRepository):
        self.repository = repository

    async def list_variants(
        self, product_id: Optional[UUID] = None
    ) -> List[ProductVariantPublicSchema]:
        if product_id is None:
            return await self.repository.get_all()
        return await self.repository.get_by_product(product_id)

    async def get_variant_by_id(self, variant_id: UUID) -> Optional[ProductVariantPublicSchema]:
        return await self.repository.get_by_id(variant_id)
