import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import PricingTier, Product, ProductVariant
from src.repositories.base_repository import BaseRepository
from src.repositories.catalog._published import purchasable
from src.schemas.catalog.pricing_tier_schema import PricingTierResponseSchema

DEFAULT_LIMIT = 100


class PricingTierRepository(BaseRepository[PricingTier, PricingTierResponseSchema]):
    """Leitura pública das tabelas de preço: só variações publicadas e confirmadas."""

    def __init__(self, session: AsyncSession):
        super().__init__(
            model=PricingTier, response_schema=PricingTierResponseSchema, session=session
        )

    @staticmethod
    def _public_query():
        return (
            select(PricingTier)
            .join(ProductVariant, ProductVariant.id == PricingTier.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(Product.deleted_at.is_(None), purchasable(ProductVariant, Product))
        )

    async def get_by_id(self, id: uuid.UUID) -> Optional[PricingTierResponseSchema]:
        result = await self.session.execute(self._public_query().where(PricingTier.id == id))
        tier = result.scalar_one_or_none()
        return self.response_schema.model_validate(tier) if tier else None

    async def list_public(
        self,
        product_id: Optional[uuid.UUID] = None,
        variant_id: Optional[uuid.UUID] = None,
    ) -> List[PricingTierResponseSchema]:
        query = self._public_query()
        if product_id is not None:
            query = query.where(ProductVariant.product_id == product_id)
        if variant_id is not None:
            query = query.where(PricingTier.variant_id == variant_id)
        query = query.order_by(PricingTier.variant_id, PricingTier.min_quantity, PricingTier.id)
        if product_id is None and variant_id is None:
            query = query.limit(DEFAULT_LIMIT)
        result = await self.session.execute(query)
        return [self.response_schema.model_validate(t) for t in result.scalars().all()]
