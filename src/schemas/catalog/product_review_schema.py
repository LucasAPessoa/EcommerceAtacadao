from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class ProductReviewBaseSchema(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    is_approved: bool = True


class ProductReviewCreateSchema(BaseModel):
    """Payload do cliente: autor e moderação são definidos pelo servidor.
    extra=forbid -> campos como user_id/is_approved geram 422 (falha explícita)."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ProductReviewUpdateSchema(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None
    is_approved: Optional[bool] = None


class ProductReviewResponseSchema(ProductReviewBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    user_id: UUID
    model_config = ConfigDict(from_attributes=True)
