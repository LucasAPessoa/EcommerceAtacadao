from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_review_schema import ProductReviewCreateSchema, ProductReviewUpdateSchema, ProductReviewResponseSchema
from src.repositories.catalog.product_review_repository import ProductReviewRepository
from src.services.catalog.product_review_service import ProductReviewService

router = APIRouter(prefix="/reviews", tags=["Product Reviews"])

def get_review_service(session: AsyncSession = Depends(get_db)) -> ProductReviewService:
    repository = ProductReviewRepository(session)
    return ProductReviewService(repository)

@router.post("/", response_model=BaseResponse[ProductReviewResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_review(
    review_in: ProductReviewCreateSchema,
    service: ProductReviewService = Depends(get_review_service)
):
    data = await service.create_review(review_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductReviewResponseSchema]])
async def list_reviews(service: ProductReviewService = Depends(get_review_service)):
    data = await service.list_reviews()
    return BaseResponse(status="success", data=data)

@router.get("/{review_id}", response_model=BaseResponse[ProductReviewResponseSchema])
async def get_review(review_id: UUID, service: ProductReviewService = Depends(get_review_service)):
    data = await service.get_review_by_id(review_id)
    if not data:
        raise HTTPException(status_code=404, detail="Review não encontrada.")
    return BaseResponse(status="success", data=data)

@router.patch("/{review_id}", response_model=BaseResponse[ProductReviewResponseSchema])
async def update_review(
    review_id: UUID, 
    review_in: ProductReviewUpdateSchema, 
    service: ProductReviewService = Depends(get_review_service)
):
    data = await service.update_review(review_id, review_in)
    if not data:
        raise HTTPException(status_code=404, detail="Review não encontrada.")
    return BaseResponse(status="success", data=data)

@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(review_id: UUID, service: ProductReviewService = Depends(get_review_service)):
    success = await service.delete_review(review_id)
    if not success:
        raise HTTPException(status_code=404, detail="Review não encontrada.")