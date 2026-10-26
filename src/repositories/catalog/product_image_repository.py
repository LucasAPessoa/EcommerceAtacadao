from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import ProductImage, ProductVariant
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.product_image_schema import ProductImageResponseSchema


class ProductImageRepository(BaseRepository[ProductImage, ProductImageResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductImage, response_schema=ProductImageResponseSchema, session=session
        )

    async def get_filtered(
        self, product_id: Optional[UUID] = None, variant_id: Optional[UUID] = None
    ) -> List[ProductImageResponseSchema]:
        """Imagens do produto (todas as variações) e/ou da variação; filtros combinam (AND)."""
        query = select(ProductImage)
        if product_id is not None:
            query = query.join(ProductVariant, ProductVariant.id == ProductImage.variant_id).where(
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
        if variant_id is not None:
            query = query.where(ProductImage.variant_id == variant_id)
        result = await self.session.execute(
            query.order_by(ProductImage.created_at, ProductImage.id)
        )
        return [self.response_schema.model_validate(o) for o in result.scalars().all()]
