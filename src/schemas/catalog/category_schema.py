from pydantic import BaseModel
from typing import Optional

class CategoryBaseSchema(BaseModel):
    name: str
    description: Optional[str]
    is_active: Optional[bool] = True

class CategoryCreateSchema(CategoryBaseSchema):
    pass

class CategoryUpdateSchema(CategoryBaseSchema):
    id: int

class CategoryResponseSchema(CategoryBaseSchema):
    id: int

    class Config:
        from_attributes = True
