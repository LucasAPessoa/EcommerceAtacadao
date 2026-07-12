from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ProductQuestionBaseSchema(BaseModel):
    question_text: str
    answer_text: Optional[str] = None

class ProductQuestionCreateSchema(ProductQuestionBaseSchema):
    product_id: UUID
    user_id: UUID

class ProductQuestionUpdateSchema(BaseModel):
    question_text: Optional[str] = None
    answer_text: Optional[str] = None

class ProductQuestionResponseSchema(ProductQuestionBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    user_id: UUID
    model_config = ConfigDict(from_attributes=True)