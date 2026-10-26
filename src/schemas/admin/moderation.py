"""Schemas do portal admin para moderação (contracts/http-api.md, seção Moderação)."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    ALL = "all"


class QuestionStatus(str, Enum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    ALL = "all"


class ModerationProduct(BaseModel):
    id: UUID
    name: str


class ModerationAuthor(BaseModel):
    id: UUID
    full_name: str


class AdminReviewItem(BaseModel):
    id: UUID
    rating: int
    comment: Optional[str] = None
    is_approved: bool
    created_at: datetime
    product: ModerationProduct
    author: ModerationAuthor

    model_config = ConfigDict(from_attributes=True)


class AdminQuestionItem(BaseModel):
    id: UUID
    question_text: str
    answer_text: Optional[str] = None
    created_at: datetime
    product: ModerationProduct
    author: ModerationAuthor

    model_config = ConfigDict(from_attributes=True)
