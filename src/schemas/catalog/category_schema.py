from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import SoftDeleteMixinSchema

class CategoryBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    name: str = Field(..., max_length=100, description="Nome da categoria")
    description: Optional[str] = None
    is_active: bool = True

class CategoryCreateSchema(CategoryBaseSchema):
    pass

class CategoryUpdateSchema(BaseModel):
    bling_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CategoryResponseSchema(CategoryBaseSchema, SoftDeleteMixinSchema):
    id: UUID
    model_config = ConfigDict(from_attributes=True)