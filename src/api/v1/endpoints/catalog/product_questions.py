from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import get_db
from src.repositories.catalog.product_question_repository import ProductQuestionRepository
from src.schemas.catalog.product_question_schema import (
    ProductQuestionCreateSchema,
    ProductQuestionResponseSchema,
    ProductQuestionUpdateSchema,
)
from src.services.catalog.product_question_service import ProductQuestionService


def get_product_question_service(session: AsyncSession = Depends(get_db)) -> ProductQuestionService:
    repository = ProductQuestionRepository(session)
    return ProductQuestionService(repository)


# Criar pergunta: qualquer cliente autenticado pode.
# Atualizar (responder) / excluir: só admin (responder pergunta é ação do vendedor).
router = build_crud_router(
    prefix="/product-questions",
    tags=["Product Questions"],
    service_dependency=get_product_question_service,
    create_schema=ProductQuestionCreateSchema,
    update_schema=ProductQuestionUpdateSchema,
    response_schema=ProductQuestionResponseSchema,
    verbs={
        "create": "create_question",
        "list": "list_questions",
        "get": "get_question_by_id",
        "update": "update_question",
        "delete": "delete_question",
    },
    not_found_message="Pergunta não encontrada.",
    write_roles=["admin"],
    create_as_author=True,
)
