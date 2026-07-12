from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ProductImageBaseSchema(BaseModel):
    image_url: str = Field(..., max_length=255)
    is_main: bool = False

class ProductImageCreateSchema(ProductImageBaseSchema):
    variant_id: UUID

class ProductImageUpdateSchema(BaseModel):
    image_url: Optional[str] = Field(None, max_length=255)
    is_main: Optional[bool] = None

class ProductImageResponseSchema(ProductImageBaseSchema, TimestampMixinSchema):
    id: UUID
    variant_id: UUID
    model_config = ConfigDict(from_attributes=True)