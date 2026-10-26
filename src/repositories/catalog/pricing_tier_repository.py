import uuid

from sqlalchemy import delete as sa_delete
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
