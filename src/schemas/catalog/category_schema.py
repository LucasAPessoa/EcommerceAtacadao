from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import Optional

class CategoryBaseSchema(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class CategoryCreateSchema(CategoryBaseSchema):
    pass

class CategoryUpdateSchema(CategoryBaseSchema):
    pass 
class CategoryResponseSchema(CategoryBaseSchema):
    id: UUID
    created_at: datetime
   
    model_config = ConfigDict(from_attributes=True)