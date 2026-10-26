from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class ProductImageBaseSchema(BaseModel):
    image_url: str = Field(..., max_length=255)
    is_main: bool = False


class ProductImageResponseSchema(ProductImageBaseSchema, TimestampMixinSchema):
    id: UUID
    variant_id: UUID
    model_config = ConfigDict(from_attributes=True)
