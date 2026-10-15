from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.schemas.base_schema import TimestampMixinSchema


class ProductQuestionBaseSchema(BaseModel):
    question_text: str
    answer_text: Optional[str] = None

class ProductQuestionCreateSchema(BaseModel):
    """Payload do cliente: autor e resposta são definidos pelo servidor.
    extra=forbid -> user_id/answer_text geram 422."""
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    question_text: str

class ProductQuestionUpdateSchema(BaseModel):
    question_text: Optional[str] = None
    answer_text: Optional[str] = None

class ProductQuestionResponseSchema(ProductQuestionBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    user_id: UUID
    model_config = ConfigDict(from_attributes=True)