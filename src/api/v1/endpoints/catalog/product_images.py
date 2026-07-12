from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_image_schema import ProductImageCreateSchema, ProductImageUpdateSchema, ProductImageResponseSchema
from src.repositories.catalog.product_image_repository import ProductImageRepository
from src.services.catalog.product_image_service import ProductImageService

router = APIRouter(prefix="/product-images", tags=["Product Images"])

def get_image_service(session: AsyncSession = Depends(get_db)) -> ProductImageService:
    repository = ProductImageRepository(session)
    return ProductImageService(repository)

@router.post("/", response_model=BaseResponse[ProductImageResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_image(
    image_in: ProductImageCreateSchema,
    service: ProductImageService = Depends(get_image_service)
):
    data = await service.create_image(image_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductImageResponseSchema]])
async def list_images(service: ProductImageService = Depends(get_image_service)):
    data = await service.list_images()
    return BaseResponse(status="success", data=data)

@router.get("/{image_id}", response_model=BaseResponse[ProductImageResponseSchema])
async def get_image(image_id: UUID, service: ProductImageService = Depends(get_image_service)):
    data = await service.get_image_by_id(image_id)
    if not data:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    return BaseResponse(status="success", data=data)

@router.patch("/{image_id}", response_model=BaseResponse[ProductImageResponseSchema])
async def update_image(
    image_id: UUID, 
    image_in: ProductImageUpdateSchema, 
    service: ProductImageService = Depends(get_image_service)
):
    data = await service.update_image(image_id, image_in)
    if not data:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    return BaseResponse(status="success", data=data)

@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(image_id: UUID, service: ProductImageService = Depends(get_image_service)):
    success = await service.delete_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")