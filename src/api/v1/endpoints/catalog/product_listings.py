from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_listing_schema import ProductListingCreateSchema, ProductListingUpdateSchema, ProductListingResponseSchema
from src.repositories.catalog.product_listing_repository import ProductListingRepository
from src.services.catalog.product_listing_service import ProductListingService

router = APIRouter(prefix="/listings", tags=["Marketplace Listings"])

def get_listing_service(session: AsyncSession = Depends(get_db)) -> ProductListingService:
    repository = ProductListingRepository(session)
    return ProductListingService(repository)

@router.post("/", response_model=BaseResponse[ProductListingResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_listing(
    listing_in: ProductListingCreateSchema,
    service: ProductListingService = Depends(get_listing_service)
):
    data = await service.create_listing(listing_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductListingResponseSchema]])
async def list_listings(service: ProductListingService = Depends(get_listing_service)):
    data = await service.list_listings()
    return BaseResponse(status="success", data=data)

@router.get("/{listing_id}", response_model=BaseResponse[ProductListingResponseSchema])
async def get_listing(listing_id: UUID, service: ProductListingService = Depends(get_listing_service)):
    data = await service.get_listing_by_id(listing_id)
    if not data:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado.")
    return BaseResponse(status="success", data=data)

@router.patch("/{listing_id}", response_model=BaseResponse[ProductListingResponseSchema])
async def update_listing(
    listing_id: UUID, 
    listing_in: ProductListingUpdateSchema, 
    service: ProductListingService = Depends(get_listing_service)
):
    data = await service.update_listing(listing_id, listing_in)
    if not data:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado.")
    return BaseResponse(status="success", data=data)

@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(listing_id: UUID, service: ProductListingService = Depends(get_listing_service)):
    success = await service.delete_listing(listing_id)
    if not success:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado.")