from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.listing_attribute_schema import ListingAttributeCreateSchema, ListingAttributeUpdateSchema, ListingAttributeResponseSchema
from src.repositories.catalog.listing_attribute_repository import ListingAttributeRepository
from src.services.catalog.listing_attribute_service import ListingAttributeService

router = APIRouter(prefix="/listing-attributes", tags=["Listing Attributes"])

def get_attribute_service(session: AsyncSession = Depends(get_db)) -> ListingAttributeService:
    repository = ListingAttributeRepository(session)
    return ListingAttributeService(repository)

@router.post("/", response_model=BaseResponse[ListingAttributeResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_attribute(
    attribute_in: ListingAttributeCreateSchema,
    service: ListingAttributeService = Depends(get_attribute_service)
):
    data = await service.create_attribute(attribute_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ListingAttributeResponseSchema]])
async def list_attributes(service: ListingAttributeService = Depends(get_attribute_service)):
    data = await service.list_attributes()
    return BaseResponse(status="success", data=data)

@router.get("/{attribute_id}", response_model=BaseResponse[ListingAttributeResponseSchema])
async def get_attribute(attribute_id: UUID, service: ListingAttributeService = Depends(get_attribute_service)):
    data = await service.get_attribute_by_id(attribute_id)
    if not data:
        raise HTTPException(status_code=404, detail="Atributo não encontrado.")
    return BaseResponse(status="success", data=data)

@router.patch("/{attribute_id}", response_model=BaseResponse[ListingAttributeResponseSchema])
async def update_attribute(
    attribute_id: UUID, 
    attribute_in: ListingAttributeUpdateSchema, 
    service: ListingAttributeService = Depends(get_attribute_service)
):
    data = await service.update_attribute(attribute_id, attribute_in)
    if not data:
        raise HTTPException(status_code=404, detail="Atributo não encontrado.")
    return BaseResponse(status="success", data=data)

@router.delete("/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(attribute_id: UUID, service: ListingAttributeService = Depends(get_attribute_service)):
    success = await service.delete_attribute(attribute_id)
    if not success:
        raise HTTPException(status_code=404, detail="Atributo não encontrado.")