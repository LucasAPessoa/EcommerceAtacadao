from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class AddressCreateSchema(BaseModel):
    zip_code: str = Field(min_length=8, max_length=10)
    street: str = Field(min_length=1, max_length=200)
    number: Optional[str] = Field(None, max_length=20)
    complement: Optional[str] = Field(None, max_length=100)
    neighborhood: Optional[str] = Field(None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    is_default: bool = False


class AddressUpdateSchema(BaseModel):
    zip_code: Optional[str] = Field(None, min_length=8, max_length=10)
    street: Optional[str] = Field(None, min_length=1, max_length=200)
    number: Optional[str] = Field(None, max_length=20)
    complement: Optional[str] = Field(None, max_length=100)
    neighborhood: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=2)


class AddressResponseSchema(TimestampMixinSchema):
    id: UUID
    user_id: UUID
    zip_code: str
    street: str
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: str
    state: str
    is_default: bool

    model_config = ConfigDict(from_attributes=True)
