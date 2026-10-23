from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class ListingImageBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    url: str = Field(..., max_length=500)
    sort_order: int = Field(..., ge=0)
    image_type: str = Field(..., max_length=50)


class ListingImageResponseSchema(ListingImageBaseSchema, TimestampMixinSchema):
    id: UUID
    listing_id: UUID
    model_config = ConfigDict(from_attributes=True)
