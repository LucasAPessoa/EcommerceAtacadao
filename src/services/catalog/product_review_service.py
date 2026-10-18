from typing import List, Optional
from uuid import UUID

from src.repositories.catalog.product_review_repository import ProductReviewRepository
from src.schemas.catalog.product_review_schema import (
    ProductReviewCreateSchema,
    ProductReviewResponseSchema,
    ProductReviewUpdateSchema,
)


class ProductReviewService:
    def __init__(self, repository: ProductReviewRepository):
        self.repository = repository

    async def create_review(
        self, review_in: ProductReviewCreateSchema, user_id: UUID
    ) -> ProductReviewResponseSchema:
        """Regras de negócio para avaliações de produtos."""
        
        # O Pydantic já validou o range (1 a 5) pelo schema, mas aqui entra a lógica extra
        if review_in.comment and len(review_in.comment.strip()) < 5:
            raise ValueError(
                "Se for deixar um comentário, ele deve ter pelo menos 5 caracteres, bo."
            )

        data = review_in.model_dump()
        data["user_id"] = user_id  # autor = usuário autenticado
        data["is_approved"] = False  # moderação é exclusiva de admin (PATCH)
        return await self.repository.create(data)

    async def list_reviews(
        self, include_unapproved: bool = False
    ) -> List[ProductReviewResponseSchema]:
        return await self.repository.get_all(only_approved=not include_unapproved)

    async def get_review_by_id(
        self, review_id: UUID, include_unapproved: bool = False
    ) -> Optional[ProductReviewResponseSchema]:
        return await self.repository.get_by_id(review_id, only_approved=not include_unapproved)

    async def update_review(
        self, review_id: UUID, review_in: ProductReviewUpdateSchema
    ) -> Optional[ProductReviewResponseSchema]:
        data = review_in.model_dump(exclude_unset=True)
        return await self.repository.update(review_id, data)

    async def delete_review(self, review_id: UUID) -> bool:
        return await self.repository.delete(review_id)