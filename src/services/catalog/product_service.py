from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_schema import ProductCreateSchema, ProductUpdateSchema, ProductResponseSchema
from src.repositories.catalog.product_repository import ProductRepository

class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def create_product(self, product_in: ProductCreateSchema) -> ProductResponseSchema:
        """Regras de negócio fortes: garante a integridade dos dados que vêm do Bling."""
        
        if not product_in.name or not product_in.name.strip():
            raise ValueError("¡Pah! O nome do produto não pode ser vazio, che.")
            
        if not product_in.code or not product_in.code.strip():
            raise ValueError("O código (SKU raiz) do produto é obrigatório para manter a sincronia com o Bling.")
            
        if product_in.product_type and len(product_in.product_type) > 10:
            raise ValueError("O tipo do produto não pode exceder 10 caracteres.")
            

        data = product_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_products(self, skip: int = 0, limit: int = 100) -> List[ProductResponseSchema]:
        return await self.repository.get_all(skip=skip, limit=limit)

    async def get_product_by_id(self, product_id: UUID) -> Optional[ProductResponseSchema]:
        return await self.repository.get_by_id(product_id)

    async def update_product(self, product_id: UUID, product_in: ProductUpdateSchema) -> Optional[ProductResponseSchema]:
        # Regra: Não permitir a alteração do SKU raiz (code) via PATCH para não quebrar a sincronia
        if product_in.code is not None:
             raise ValueError("O código (SKU raiz) do produto é imutável após a criação, bo.")
             
        data = product_in.model_dump(exclude_unset=True)
        return await self.repository.update(product_id, data)

    async def delete_product(self, product_id: UUID) -> bool:
        return await self.repository.delete(product_id)