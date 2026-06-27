from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.catalog.category_schema import CategoryBaseSchema, CategoryCreateSchema, CategoryResponseSchema
from src.repositories.catalog.category_repository import CategoryRepository
from src.schemas.response_schema import BaseResponse
from src.services.catalog.category_service import CategoryService

router = APIRouter()

def get_category_service(session: AsyncSession = Depends(get_db)) -> BaseResponse[CategoryResponseSchema]:
    """Função de dependência para obter uma instância do CategoryService."""
    repository = CategoryRepository(session)
    return CategoryService(repository)

@router.post("/categories", response_model=BaseResponse[CategoryResponseSchema], tags=["Categories"], status_code=201)
async def create_category(
    category_in: CategoryCreateSchema,
    service: CategoryService = Depends(get_category_service)
):
    try:
        data = await service.create_category(category_in)
        return BaseResponse[CategoryResponseSchema](data=data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))