"""Listagens de moderação do portal admin (avaliações e perguntas)."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import Product, ProductQuestion, ProductReview
from src.models.identity import User
from src.schemas.admin.moderation import QuestionStatus, ReviewStatus


class ModerationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _page(
        self, model: Any, where: list[Any], skip: int, limit: int
    ) -> tuple[list[Any], int]:
        def joined(stmt: Select[Any]) -> Select[Any]:
            return (
                stmt.join(Product, Product.id == model.product_id)
                .join(User, User.id == model.user_id)
                .where(*where)
            )

        total = (await self.session.execute(joined(select(func.count(model.id))))).scalar_one()
        stmt = (
            joined(select(model, Product.name, User.full_name))
            .order_by(model.created_at.desc(), model.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [tuple(r) for r in (await self.session.execute(stmt)).all()], int(total)

    async def list_reviews(
        self, status: ReviewStatus, product_id: Optional[UUID], skip: int, limit: int
    ) -> tuple[list[Any], int]:
        where: list[Any] = []
        if status is ReviewStatus.PENDING:
            where.append(ProductReview.is_approved.is_(False))
        elif status is ReviewStatus.APPROVED:
            where.append(ProductReview.is_approved.is_(True))
        if product_id is not None:
            where.append(ProductReview.product_id == product_id)
        return await self._page(ProductReview, where, skip, limit)

    async def list_questions(
        self, status: QuestionStatus, product_id: Optional[UUID], skip: int, limit: int
    ) -> tuple[list[Any], int]:
        blank = or_(
            ProductQuestion.answer_text.is_(None), func.btrim(ProductQuestion.answer_text) == ""
        )
        where: list[Any] = []
        if status is QuestionStatus.UNANSWERED:
            where.append(blank)
        elif status is QuestionStatus.ANSWERED:
            where.append(~blank)
        if product_id is not None:
            where.append(ProductQuestion.product_id == product_id)
        return await self._page(ProductQuestion, where, skip, limit)
