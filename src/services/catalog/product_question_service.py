from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_question_schema import ProductQuestionCreateSchema, ProductQuestionUpdateSchema, ProductQuestionResponseSchema
from src.repositories.catalog.product_question_repository import ProductQuestionRepository

class ProductQuestionService:
    def __init__(self, repository: ProductQuestionRepository):
        self.repository = repository

    async def create_question(self, question_in: ProductQuestionCreateSchema) -> ProductQuestionResponseSchema:
        """Regras de negócio para perguntas e respostas."""
        
        if not question_in.question_text.strip():
            raise ValueError("A pergunta não pode estar vazia.")
            
        if question_in.answer_text is not None and not question_in.answer_text.strip():
            raise ValueError("Se a resposta for enviada, não pode ser vazia.")

        data = question_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_questions(self) -> List[ProductQuestionResponseSchema]:
        return await self.repository.get_all()

    async def get_question_by_id(self, question_id: UUID) -> Optional[ProductQuestionResponseSchema]:
        return await self.repository.get_by_id(question_id)

    async def update_question(self, question_id: UUID, question_in: ProductQuestionUpdateSchema) -> Optional[ProductQuestionResponseSchema]:
        data = question_in.model_dump(exclude_unset=True)
        return await self.repository.update(question_id, data)

    async def delete_question(self, question_id: UUID) -> bool:
        return await self.repository.delete(question_id)