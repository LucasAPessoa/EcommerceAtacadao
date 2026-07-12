from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.schemas.response_schema import BaseResponse
from src.schemas.catalog.product_question_schema import ProductQuestionCreateSchema, ProductQuestionUpdateSchema, ProductQuestionResponseSchema
from src.repositories.catalog.product_question_repository import ProductQuestionRepository
from src.services.catalog.product_question_service import ProductQuestionService

router = APIRouter(prefix="/questions", tags=["Product Questions"])

def get_question_service(session: AsyncSession = Depends(get_db)) -> ProductQuestionService:
    repository = ProductQuestionRepository(session)
    return ProductQuestionService(repository)

@router.post("/", response_model=BaseResponse[ProductQuestionResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_question(
    question_in: ProductQuestionCreateSchema,
    service: ProductQuestionService = Depends(get_question_service)
):
    data = await service.create_question(question_in)
    return BaseResponse(status="success", data=data)

@router.get("/", response_model=BaseResponse[list[ProductQuestionResponseSchema]])
async def list_questions(service: ProductQuestionService = Depends(get_question_service)):
    data = await service.list_questions()
    return BaseResponse(status="success", data=data)

@router.get("/{question_id}", response_model=BaseResponse[ProductQuestionResponseSchema])
async def get_question(question_id: UUID, service: ProductQuestionService = Depends(get_question_service)):
    data = await service.get_question_by_id(question_id)
    if not data:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    return BaseResponse(status="success", data=data)

@router.patch("/{question_id}", response_model=BaseResponse[ProductQuestionResponseSchema])
async def update_question(
    question_id: UUID, 
    question_in: ProductQuestionUpdateSchema, 
    service: ProductQuestionService = Depends(get_question_service)
):
    data = await service.update_question(question_id, question_in)
    if not data:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    return BaseResponse(status="success", data=data)

@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: UUID, service: ProductQuestionService = Depends(get_question_service)):
    success = await service.delete_question(question_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")