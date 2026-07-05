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
    pass # O ID vai na URL, não precisamos dele no corpo do Update

class CategoryResponseSchema(CategoryBaseSchema):
    id: UUID
    created_at: datetime
    # deleted_at geralmente não é devolvido para o front-end

    # Sintaxe correta do Pydantic V2 para converter Models SQLAlchemy em JSON
    model_config = ConfigDict(from_attributes=True)