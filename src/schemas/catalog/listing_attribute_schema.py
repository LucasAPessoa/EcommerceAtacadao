from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ListingAttributeBaseSchema(BaseModel):
    bling_external_id: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=100)
    attribute_type: str = Field(..., max_length=50)
    value: str = Field(..., max_length=255)
    unit: Optional[str] = Field(None, max_length=50)

class ListingAttributeCreateSchema(ListingAttributeBaseSchema):
    listing_id: UUID

class ListingAttributeUpdateSchema(BaseModel):
    bling_external_id: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    attribute_type: Optional[str] = Field(None, max_length=50)
    value: Optional[str] = Field(None, max_length=255)
    unit: Optional[str] = Field(None, max_length=50)

class ListingAttributeResponseSchema(ListingAttributeBaseSchema, TimestampMixinSchema):
    id: UUID
    listing_id: UUID
    model_config = ConfigDict(from_attributes=True)