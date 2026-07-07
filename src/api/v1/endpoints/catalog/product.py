from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db import get_db
from src.schemas.catalog.product_schema import ProductBaseSchema, ProductCreateSchema, ProductResponseSchema
from src.repositories.catalog.product_repository import ProductRepository
from src.schemas.response_schema import BaseResponse
from src.services.catalog.product_service import ProductService


router = APIRouter()


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    repository = ProductRepository(session)
    return ProductService(repository)


@router.post("/products", response_model=BaseResponse[ProductResponseSchema], tags=["Products"], status_code=201)
async def create_product(
    product_in: ProductCreateSchema,
    service: ProductService = Depends(get_product_service)
):
    data = await service.create_product(product_in)
    return BaseResponse(status="success", data=data)