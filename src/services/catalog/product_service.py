from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_repository import ProductRepository
from src.schemas.catalog.product_schema import (
    ProductResponseSchema,
)


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def list_products(
        self,
        skip: int = 0,
        limit: int = 100,
        category_id: Optional[UUID] = None,
        featured: Optional[bool] = None,
    ) -> List[ProductResponseSchema]:
        return await self.repository.get_all(
            skip=skip, limit=limit, category_id=category_id, featured=featured
        )

    async def get_product_by_id(self, product_id: UUID) -> Optional[ProductResponseSchema]:
        return await self.repository.get_by_id(product_id)

    async def get_product_by_code(self, code: str) -> Optional[ProductResponseSchema]:
        return await self.repository.get_by_code(code)
