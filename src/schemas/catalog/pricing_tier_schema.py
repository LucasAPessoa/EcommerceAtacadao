from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class PricingTierBaseSchema(BaseModel):
    min_quantity: int
    unit_price: float

class PricingTierCreateSchema(PricingTierBaseSchema):
    product_id: UUID

class PricingTierUpdateSchema(BaseModel):
    min_quantity: Optional[int] = None
    unit_price: Optional[float] = None

class PricingTierResponseSchema(PricingTierBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)