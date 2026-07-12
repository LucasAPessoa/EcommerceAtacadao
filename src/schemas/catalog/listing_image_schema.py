from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ListingImageBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    url: str = Field(..., max_length=500)
    sort_order: int
    image_type: str = Field(..., max_length=50)

class ListingImageCreateSchema(ListingImageBaseSchema):
    listing_id: UUID

class ListingImageUpdateSchema(BaseModel):
    bling_id: Optional[int] = None
    url: Optional[str] = Field(None, max_length=500)
    sort_order: Optional[int] = None
    image_type: Optional[str] = Field(None, max_length=50)

class ListingImageResponseSchema(ListingImageBaseSchema, TimestampMixinSchema):
    id: UUID
    listing_id: UUID
    model_config = ConfigDict(from_attributes=True)