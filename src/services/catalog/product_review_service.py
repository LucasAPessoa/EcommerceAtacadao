from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_review_schema import ProductReviewCreateSchema, ProductReviewUpdateSchema, ProductReviewResponseSchema
from src.repositories.catalog.product_review_repository import ProductReviewRepository

class ProductReviewService:
    def __init__(self, repository: ProductReviewRepository):
        self.repository = repository

    async def create_review(self, review_in: ProductReviewCreateSchema) -> ProductReviewResponseSchema:
        """Regras de negócio para avaliações de produtos."""
        
        # O Pydantic já validou o range (1 a 5) pelo schema, mas aqui entra a lógica extra
        if review_in.comment and len(review_in.comment.strip()) < 5:
            raise ValueError("Se for deixar um comentário, ele deve ter pelo menos 5 caracteres, bo.")

        data = review_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_reviews(self) -> List[ProductReviewResponseSchema]:
        return await self.repository.get_all()

    async def get_review_by_id(self, review_id: UUID) -> Optional[ProductReviewResponseSchema]:
        return await self.repository.get_by_id(review_id)

    async def update_review(self, review_id: UUID, review_in: ProductReviewUpdateSchema) -> Optional[ProductReviewResponseSchema]:
        data = review_in.model_dump(exclude_unset=True)
        return await self.repository.update(review_id, data)

    async def delete_review(self, review_id: UUID) -> bool:
        return await self.repository.delete(review_id)