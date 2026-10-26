from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_question_repository import ProductQuestionRepository
from src.schemas.catalog.product_question_schema import (
    ProductQuestionCreateSchema,
    ProductQuestionResponseSchema,
    ProductQuestionUpdateSchema,
)


class ProductQuestionService:
    def __init__(self, repository: ProductQuestionRepository):
        self.repository = repository

    async def create_question(
        self, question_in: ProductQuestionCreateSchema, user_id: UUID
    ) -> ProductQuestionResponseSchema:
        """Regras de negócio para perguntas e respostas."""

        if not question_in.question_text.strip():
            raise ValueError("A pergunta não pode estar vazia.")

        data = question_in.model_dump()
        data["user_id"] = user_id  # autor = usuário autenticado
        data["answer_text"] = None  # resposta é exclusiva de admin (PATCH)
        return await self.repository.create(data)

    async def list_questions(
        self, product_id: Optional[UUID] = None
    ) -> List[ProductQuestionResponseSchema]:
        if product_id is None:
            return await self.repository.get_all()
        return await self.repository.get_by_product(product_id)

    async def get_question_by_id(
        self, question_id: UUID
    ) -> Optional[ProductQuestionResponseSchema]:
        return await self.repository.get_by_id(question_id)

    async def update_question(
        self, question_id: UUID, question_in: ProductQuestionUpdateSchema
    ) -> Optional[ProductQuestionResponseSchema]:
        data = question_in.model_dump(exclude_unset=True)
        return await self.repository.update(question_id, data)

    async def delete_question(self, question_id: UUID) -> bool:
        return await self.repository.delete(question_id)
