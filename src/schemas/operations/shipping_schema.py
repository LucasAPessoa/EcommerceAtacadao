from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ShippingCalculateItemSchema(BaseModel):
    variant_id: UUID
    quantity: int = Field(gt=0)


class ShippingCalculateRequestSchema(BaseModel):
    destination_zip_code: str = Field(min_length=8, max_length=10)
    items: List[ShippingCalculateItemSchema] = Field(min_length=1)

    @field_validator("destination_zip_code")
    @classmethod
    def normalize_zip_code(cls, value: str) -> str:
        zip_code = "".join(character for character in value if character.isdigit())
        if len(zip_code) != 8:
            raise ValueError("CEP de destino deve conter oito dígitos.")
        return zip_code


class ShippingQuoteSchema(BaseModel):
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    company_name: Optional[str] = None
    price: Decimal
    delivery_time_days: Optional[int] = None
