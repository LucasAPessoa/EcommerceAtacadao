from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import Product, ProductVariant
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.product_variant_schema import ProductVariantResponseSchema


class ProductVariantRepository(BaseRepository[ProductVariant, ProductVariantResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductVariant, response_schema=ProductVariantResponseSchema, session=session
        )

    async def get_active_for_shipping(self, variant_id: UUID) -> Optional[ProductVariant]:
        """Busca somente o SKU comercialmente disponível para uma cotação pública."""
        query = (
            select(ProductVariant)
            .join(ProductVariant.product)
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.is_active.is_(True),
                ProductVariant.deleted_at.is_(None),
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
