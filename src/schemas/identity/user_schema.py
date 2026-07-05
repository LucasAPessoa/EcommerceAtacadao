from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserBase(BaseModel):
    email: EmailStr
    is_active: bool = True
    user_type: Literal["INDIVIDUAL", "COMPANY", "ADMIN"] = "INDIVIDUAL"

    @field_validator("user_type", mode="before")
    @classmethod
    def normalize_user_type(cls, value: str) -> str:
        legacy_mapping = {
            "client": "INDIVIDUAL",
            "user": "INDIVIDUAL",
            "cpf": "INDIVIDUAL",
            "cnpj": "COMPANY",
        }
        if isinstance(value, str):
            return legacy_mapping.get(value, value)
        return value

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    corporate_name: Optional[str] = None
    ie: Optional[str] = None

    @model_validator(mode="after")
    def validate_user_type_fields(self) -> "UserCreate":
        if self.user_type == "individual":
            self.cnpj = None
            self.corporate_name = None
            self.ie = None

        if not self.cpf:
            raise ValueError("Individual users must provide cpf")

        if not self.corporate_name or not self.cnpj:
            raise ValueError("Company users must provide corporate_name and cnpj")
        return self

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class LogoutRequestSchema(BaseModel):
    refresh_token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    full_name: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    corporate_name: Optional[str] = None
    ie: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True