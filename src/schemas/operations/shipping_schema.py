from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ShippingCalculateItemSchema(BaseModel):
    variant_id: UUID
    quantity: int = Field(gt=0)


class ShippingCalculateRequestSchema(BaseModel):
    destination_zip_code: str = Field(min_length=8, max_length=10)
    items: List[ShippingCalculateItemSchema] = Field(min_length=1)


class ShippingQuoteSchema(BaseModel):
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    company_name: Optional[str] = None
    price: float
    delivery_time_days: Optional[int] = None
