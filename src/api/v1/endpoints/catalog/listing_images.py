from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.listing_image_schema import ListingImageCreateSchema, ListingImageUpdateSchema, ListingImageResponseSchema
from src.repositories.catalog.listing_image_repository import ListingImageRepository
from src.services.catalog.listing_image_service import ListingImageService

router = APIRouter(prefix="/listing-images", tags=["Listing Images"])

def get_listing_image_service(session: AsyncSession = Depends(get_db)) -> ListingImageService:
    repository = ListingImageRepository(session)
    return ListingImageService(repository)

@router.post("/", response_model=BaseResponse[ListingImageResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_listing_image(
    image_in: ListingImageCreateSchema,
    service: ListingImageService = Depends(get_listing_image_service)
):
    try:
        data = await service.create_image(image_in)
        return BaseResponse(status="success", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/", response_model=BaseResponse[list[ListingImageResponseSchema]])
async def list_listing_images(service: ListingImageService = Depends(get_listing_image_service)):
    data = await service.list_images()
    return BaseResponse(status="success", data=data)

@router.get("/{image_id}", response_model=BaseResponse[ListingImageResponseSchema])
async def get_listing_image(image_id: UUID, service: ListingImageService = Depends(get_listing_image_service)):
    data = await service.get_image_by_id(image_id) # Assumindo que tu tens o get_image_by_id no Service/Repo
    if not data:
        raise HTTPException(status_code=404, detail="Imagem do anúncio não encontrada, che.")
    return BaseResponse(status="success", data=data)

@router.patch("/{image_id}", response_model=BaseResponse[ListingImageResponseSchema])
async def update_listing_image(
    image_id: UUID, 
    image_in: ListingImageUpdateSchema, 
    service: ListingImageService = Depends(get_listing_image_service)
):
    try:
        data = await service.update_image(image_id, image_in)
        if not data:
            raise HTTPException(status_code=404, detail="Imagem do anúncio não encontrada.")
        return BaseResponse(status="success", data=data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing_image(image_id: UUID, service: ListingImageService = Depends(get_listing_image_service)):
    success = await service.delete_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Imagem do anúncio não encontrada.")