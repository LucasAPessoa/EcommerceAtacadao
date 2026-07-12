from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.base_repository import BaseRepository
from src.models.catalog import PricingTier
from src.schemas.catalog.pricing_tier_schema import PricingTierResponseSchema

class PricingTierRepository(BaseRepository[PricingTier, PricingTierResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=PricingTier, 
            response_schema=PricingTierResponseSchema, 
            session=session
        )