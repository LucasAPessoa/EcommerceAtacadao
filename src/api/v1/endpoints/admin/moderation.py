from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from src.api.v1.endpoints.admin._params import PageParams, page_params
from src.core.db import DbSession
from src.repositories.admin.moderation_repository import ModerationRepository
from src.schemas.admin.moderation import (
    AdminQuestionItem,
    AdminReviewItem,
    ModerationAuthor,
    ModerationProduct,
    QuestionStatus,
    ReviewStatus,
)
from src.schemas.response_schema import BaseResponse, PageMeta

router = APIRouter(prefix="/moderation", tags=["Admin - Moderation"])


def get_moderation_repository(session: DbSession) -> ModerationRepository:
    return ModerationRepository(session)


def _common(obj, name: str, author: str) -> dict:
    return {
        "id": obj.id,
        "created_at": obj.created_at,
        "product": ModerationProduct(id=obj.product_id, name=name),
        "author": ModerationAuthor(id=obj.user_id, full_name=author),
    }


@router.get("/reviews", response_model=BaseResponse[list[AdminReviewItem]])
async def list_reviews(
    status: ReviewStatus = ReviewStatus.PENDING,
    product_id: Optional[UUID] = None,
    page: PageParams = Depends(page_params),
    repo: ModerationRepository = Depends(get_moderation_repository),
):
    rows, total = await repo.list_reviews(status, product_id, page.skip, page.limit)
    items = [
        AdminReviewItem(
            **_common(r, name, author),
            rating=r.rating,
            comment=r.comment,
            is_approved=r.is_approved,
        )
        for r, name, author in rows
    ]
    return BaseResponse(data=items, meta=PageMeta(total=total, skip=page.skip, limit=page.limit))


@router.get("/questions", response_model=BaseResponse[list[AdminQuestionItem]])
async def list_questions(
    status: QuestionStatus = QuestionStatus.UNANSWERED,
    product_id: Optional[UUID] = None,
    page: PageParams = Depends(page_params),
    repo: ModerationRepository = Depends(get_moderation_repository),
):
    rows, total = await repo.list_questions(status, product_id, page.skip, page.limit)
    items = [
        AdminQuestionItem(
            **_common(q, name, author), question_text=q.question_text, answer_text=q.answer_text
        )
        for q, name, author in rows
    ]
    return BaseResponse(data=items, meta=PageMeta(total=total, skip=page.skip, limit=page.limit))
