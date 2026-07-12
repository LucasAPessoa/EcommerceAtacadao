from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_schema import ProductCreateSchema, ProductUpdateSchema, ProductResponseSchema
from src.repositories.catalog.product_repository import ProductRepository
from src.services.catalog.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])

def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    repository = ProductRepository(session)
    return ProductService(repository)

@router.post("/", response_model=BaseResponse[ProductResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreateSchema,
    service: ProductService = Depends(get_product_service)
):
    data = await service.create_product(product_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductResponseSchema]])
async def list_products(
    skip: int = 0, 
    limit: int = 100, 
    service: ProductService = Depends(get_product_service)
):
    data = await service.list_products(skip=skip, limit=limit)
    return BaseResponse(status="success", data=data)

@router.get("/{product_id}", response_model=BaseResponse[ProductResponseSchema])
async def get_product(product_id: UUID, service: ProductService = Depends(get_product_service)):
    data = await service.get_product_by_id(product_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado, che.")
    return BaseResponse(status="success", data=data)

@router.patch("/{product_id}", response_model=BaseResponse[ProductResponseSchema])
async def update_product(
    product_id: UUID, 
    product_in: ProductUpdateSchema, 
    service: ProductService = Depends(get_product_service)
):
    try:
        data = await service.update_product(product_id, product_in)
        if not data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado para atualização.")
        return BaseResponse(status="success", data=data)
    except ValueError as e:
        # Pega as validações de regra de negócio do Service (ex: tentar atualizar SKU) e devolve um 400 Bad Request
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, service: ProductService = Depends(get_product_service)):
    success = await service.delete_product(product_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")