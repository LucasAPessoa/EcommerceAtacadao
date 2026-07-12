from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.pricing_tier_schema import PricingTierCreateSchema, PricingTierUpdateSchema, PricingTierResponseSchema
from src.repositories.catalog.pricing_tier_repository import PricingTierRepository
from src.services.catalog.pricing_tier_service import PricingTierService

router = APIRouter(prefix="/pricing-tiers", tags=["Pricing Tiers"])

def get_tier_service(session: AsyncSession = Depends(get_db)) -> PricingTierService:
    repository = PricingTierRepository(session)
    return PricingTierService(repository)

@router.post("/", response_model=BaseResponse[PricingTierResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_tier(
    tier_in: PricingTierCreateSchema,
    service: PricingTierService = Depends(get_tier_service)
):
    data = await service.create_tier(tier_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[PricingTierResponseSchema]])
async def list_tiers(service: PricingTierService = Depends(get_tier_service)):
    data = await service.list_tiers()
    return BaseResponse(status="success", data=data)

@router.get("/{tier_id}", response_model=BaseResponse[PricingTierResponseSchema])
async def get_tier(tier_id: UUID, service: PricingTierService = Depends(get_tier_service)):
    data = await service.get_tier_by_id(tier_id) # Omitido no snippet do service, mas tu tens o repo!
    if not data:
        raise HTTPException(status_code=404, detail="Tier não encontrado.")
    return BaseResponse(status="success", data=data)

@router.patch("/{tier_id}", response_model=BaseResponse[PricingTierResponseSchema])
async def update_tier(
    tier_id: UUID, 
    tier_in: PricingTierUpdateSchema, 
    service: PricingTierService = Depends(get_tier_service)
):
    data = await service.update_tier(tier_id, tier_in)
    if not data:
        raise HTTPException(status_code=404, detail="Tier não encontrado.")
    return BaseResponse(status="success", data=data)

@router.delete("/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(tier_id: UUID, service: PricingTierService = Depends(get_tier_service)):
    success = await service.delete_tier(tier_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tier não encontrado.")