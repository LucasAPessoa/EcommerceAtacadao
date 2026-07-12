from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ProductReviewBaseSchema(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    is_approved: bool = True

class ProductReviewCreateSchema(ProductReviewBaseSchema):
    product_id: UUID
    user_id: UUID

class ProductReviewUpdateSchema(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None
    is_approved: Optional[bool] = None

class ProductReviewResponseSchema(ProductReviewBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    user_id: UUID
    model_config = ConfigDict(from_attributes=True)