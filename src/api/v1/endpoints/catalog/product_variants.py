from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_variant_schema import ProductVariantCreateSchema, ProductVariantUpdateSchema, ProductVariantResponseSchema
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.services.catalog.product_variant_service import ProductVariantService

router = APIRouter(prefix="/variants", tags=["Product Variants"])

def get_variant_service(session: AsyncSession = Depends(get_db)) -> ProductVariantService:
    repository = ProductVariantRepository(session)
    return ProductVariantService(repository)

@router.post("/", response_model=BaseResponse[ProductVariantResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_variant(
    variant_in: ProductVariantCreateSchema,
    service: ProductVariantService = Depends(get_variant_service)
):
    data = await service.create_variant(variant_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductVariantResponseSchema]])
async def list_variants(service: ProductVariantService = Depends(get_variant_service)):
    data = await service.list_variants()
    return BaseResponse(status="success", data=data)

@router.get("/{variant_id}", response_model=BaseResponse[ProductVariantResponseSchema])
async def get_variant(variant_id: UUID, service: ProductVariantService = Depends(get_variant_service)):
    data = await service.get_variant_by_id(variant_id)
    if not data:
        raise HTTPException(status_code=404, detail="Variação não encontrada.")
    return BaseResponse(status="success", data=data)

@router.patch("/{variant_id}", response_model=BaseResponse[ProductVariantResponseSchema])
async def update_variant(
    variant_id: UUID, 
    variant_in: ProductVariantUpdateSchema, 
    service: ProductVariantService = Depends(get_variant_service)
):
    data = await service.update_variant(variant_id, variant_in)
    if not data:
        raise HTTPException(status_code=404, detail="Variação não encontrada.")
    return BaseResponse(status="success", data=data)

@router.delete("/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(variant_id: UUID, service: ProductVariantService = Depends(get_variant_service)):
    success = await service.delete_variant(variant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Variação não encontrada.")