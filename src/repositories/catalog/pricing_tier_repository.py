import uuid
from typing import List

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import PricingTier
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.pricing_tier_schema import PricingTierResponseSchema


class PricingTierRepository(BaseRepository[PricingTier, PricingTierResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=PricingTier, response_schema=PricingTierResponseSchema, session=session
        )

    async def delete(self, id: uuid.UUID) -> bool:
        """Exclusão física: PricingTier não tem soft delete e nada o referencia."""
        result = await self.session.execute(sa_delete(PricingTier).where(PricingTier.id == id))
        await self.session.commit()
        return result.rowcount > 0  # type: ignore[attr-defined]  # CursorResult em DML

    async def get_by_product(self, product_id: uuid.UUID) -> List[PricingTierResponseSchema]:
        query = (
            select(PricingTier)
            .where(PricingTier.product_id == product_id)
            .order_by(PricingTier.min_quantity.asc())
        )
        result = await self.session.execute(query)
        return [self.response_schema.model_validate(o) for o in result.scalars().all()]
