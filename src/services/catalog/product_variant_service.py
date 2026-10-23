from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.catalog.product_variant_schema import (
    ProductVariantResponseSchema,
    ProductVariantUpdateSchema,
)


class ProductVariantService:
    def __init__(self, repository: ProductVariantRepository):
        self.repository = repository

    async def list_variants(
        self, product_id: Optional[UUID] = None
    ) -> List[ProductVariantResponseSchema]:
        if product_id is None:
            return await self.repository.get_all()
        return await self.repository.get_by_product(product_id)

    async def get_variant_by_id(self, variant_id: UUID) -> Optional[ProductVariantResponseSchema]:
        return await self.repository.get_by_id(variant_id)

    async def update_variant(
        self, variant_id: UUID, variant_in: ProductVariantUpdateSchema
    ) -> Optional[ProductVariantResponseSchema]:
        if variant_in.base_price is not None and variant_in.base_price < 0:
            raise ValueError("O preço atualizado não pode ser negativo.")

        data = variant_in.model_dump(exclude_unset=True)
        return await self.repository.update(variant_id, data)
