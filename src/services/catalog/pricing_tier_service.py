from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.pricing_tier_repository import PricingTierRepository
from src.schemas.catalog.pricing_tier_schema import PricingTierResponseSchema


class PricingTierService:
    """Somente leitura: a tabela de preços é editada pelo admin (PUT por variação)."""

    def __init__(self, repository: PricingTierRepository):
        self.repository = repository

    async def list_tiers(
        self, product_id: Optional[UUID] = None, variant_id: Optional[UUID] = None
    ) -> List[PricingTierResponseSchema]:
        return await self.repository.list_public(product_id=product_id, variant_id=variant_id)

    async def get_tier_by_id(self, tier_id: UUID) -> Optional[PricingTierResponseSchema]:
        return await self.repository.get_by_id(tier_id)
