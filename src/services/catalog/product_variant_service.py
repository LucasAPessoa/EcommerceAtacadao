from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_variant_schema import ProductVariantCreateSchema, ProductVariantUpdateSchema, ProductVariantResponseSchema
from src.repositories.catalog.product_variant_repository import ProductVariantRepository

class ProductVariantService:
    def __init__(self, repository: ProductVariantRepository):
        self.repository = repository

    async def create_variant(self, variant_in: ProductVariantCreateSchema) -> ProductVariantResponseSchema:
        """Regras de negócio para as variações (SKUs) do produto."""
        
        if not variant_in.bling_sku or not variant_in.bling_sku.strip():
            raise ValueError("A variação precisa obrigatoriamente de um SKU do Bling.")
            
        if variant_in.base_price < 0:
            raise ValueError("O preço base não pode ser negativo, che.")
            
        if variant_in.stock_quantity < 0:
            raise ValueError("O estoque não pode ser negativo.")

        data = variant_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_variants(self) -> List[ProductVariantResponseSchema]:
        return await self.repository.get_all()

    async def get_variant_by_id(self, variant_id: UUID) -> Optional[ProductVariantResponseSchema]:
        return await self.repository.get_by_id(variant_id)

    async def update_variant(self, variant_id: UUID, variant_in: ProductVariantUpdateSchema) -> Optional[ProductVariantResponseSchema]:
        if variant_in.base_price is not None and variant_in.base_price < 0:
            raise ValueError("O preço atualizado não pode ser negativo.")
            
        data = variant_in.model_dump(exclude_unset=True)
        return await self.repository.update(variant_id, data)

    async def delete_variant(self, variant_id: UUID) -> bool:
        return await self.repository.delete(variant_id)