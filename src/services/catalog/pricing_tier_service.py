from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.pricing_tier_schema import PricingTierCreateSchema, PricingTierUpdateSchema, PricingTierResponseSchema
from src.repositories.catalog.pricing_tier_repository import PricingTierRepository

class PricingTierService:
    def __init__(self, repository: PricingTierRepository):
        self.repository = repository

    async def create_tier(self, tier_in: PricingTierCreateSchema) -> PricingTierResponseSchema:
        if tier_in.min_quantity <= 1:
            raise ValueError("Para um preço de atacado (tier), a quantidade mínima deve ser maior que 1, bo.")
            
        if tier_in.unit_price <= 0:
            raise ValueError("O preço da faixa não pode ser zero ou negativo.")

        data = tier_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_tiers(self) -> List[PricingTierResponseSchema]:
        return await self.repository.get_all()

    async def get_tier_by_id(self, tier_id: UUID) -> Optional[PricingTierResponseSchema]:
        return await self.repository.get_by_id(tier_id)

    async def update_tier(self, tier_id: UUID, tier_in: PricingTierUpdateSchema) -> Optional[PricingTierResponseSchema]:
        if tier_in.min_quantity is not None and tier_in.min_quantity <= 1:
            raise ValueError("Para um preço de atacado (tier), a quantidade mínima deve ser maior que 1, bo.")
        if tier_in.unit_price is not None and tier_in.unit_price <= 0:
            raise ValueError("O preço da faixa não pode ser zero ou negativo.")

        data = tier_in.model_dump(exclude_unset=True)
        return await self.repository.update(tier_id, data)

    async def delete_tier(self, tier_id: UUID) -> bool:
        return await self.repository.delete(tier_id)
