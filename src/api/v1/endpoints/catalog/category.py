from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.catalog.category_schema import CategoryBaseSchema, CategoryCreateSchema, CategoryResponseSchema
from src.repositories.catalog.category_repository import CategoryRepository
from src.schemas.response_schema import BaseResponse
from src.services.catalog.category_service import CategoryService

router = APIRouter()

def get_category_service(session: AsyncSession = Depends(get_db)) -> CategoryService:
    repository = CategoryRepository(session)
    return CategoryService(repository)

@router.post("/categories", response_model=BaseResponse[CategoryResponseSchema], tags=["Categories"], status_code=201)
async def create_category(
    category_in: CategoryCreateSchema,
    service: CategoryService = Depends(get_category_service)
):
    data = await service.create_category(category_in)
    return BaseResponse(status="success", data=data)
  
@router.get("/categories", response_model=BaseResponse[list[CategoryResponseSchema]], tags=["Categories"])
async def list_categories(service: CategoryService = Depends(get_category_service)):
    data = await service.list_categories()
    return BaseResponse(status="success", data=data)

@router.get("/categories/{category_id}", response_model=BaseResponse[CategoryResponseSchema], tags=["Categories"])
async def get_category_by_id(
    category_id: UUID,
    service: CategoryService = Depends(get_category_service)
):
    data = await service.get_category_by_id(category_id)
    if not data:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return BaseResponse(status="success", data=data)

@router.put("/categories/{category_id}", response_model=BaseResponse[CategoryResponseSchema], tags=["Categories"])
async def update_category(
    category_id: UUID,
    category_in: CategoryBaseSchema,
    service: CategoryService = Depends(get_category_service)
):
    data = await service.update_category(category_id, category_in)
    if not data:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return BaseResponse(status="success", data=data)

@router.delete("/categories/{category_id}", response_model=BaseResponse[dict], tags=["Categories"])
async def delete_category(
    category_id: UUID,
    service: CategoryService = Depends(get_category_service)
):
    success = await service.delete_category(category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return BaseResponse(status="success", data={"message": "Categoria excluída com sucesso"})