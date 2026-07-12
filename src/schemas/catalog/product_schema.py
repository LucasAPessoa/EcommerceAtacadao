from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from uuid import UUID
from src.schemas.base_schema import SoftDeleteMixinSchema

class ProductBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    name: str = Field(..., max_length=200, description="Nome do produto")
    code: Optional[str] = Field(None, max_length=100, description="SKU raiz do produto")
    description: Optional[str] = None
    complementary_description: Optional[str] = None
    is_active: bool = False
    
    # Propriedades específicas do Bling
    product_type: Optional[str] = Field(None, max_length=10)
    format: Optional[str] = Field(None, max_length=10)
    status: Optional[str] = Field(None, max_length=10)
    brand: Optional[str] = Field(None, max_length=100)
    condition: Optional[int] = None
    unit: Optional[str] = Field(None, max_length=10)
    
    # Estruturas JSON flexíveis
    dimensions_raw: Optional[Dict[str, Any]] = None
    inventory_raw: Optional[Dict[str, Any]] = None
    media_raw: Optional[Dict[str, Any]] = None
    custom_fields: Optional[List[Dict[str, Any]]] = None

class ProductCreateSchema(ProductBaseSchema):
    # O Pydantic já herda a obrigatoriedade do 'name'.
    pass

class ProductUpdateSchema(BaseModel):
    # Tudo opcional para permitir o PATCH
    bling_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=200)
    code: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    complementary_description: Optional[str] = None
    is_active: Optional[bool] = None
    
    product_type: Optional[str] = Field(None, max_length=10)
    format: Optional[str] = Field(None, max_length=10)
    status: Optional[str] = Field(None, max_length=10)
    brand: Optional[str] = Field(None, max_length=100)
    condition: Optional[int] = None
    unit: Optional[str] = Field(None, max_length=10)
    
    dimensions_raw: Optional[Dict[str, Any]] = None
    inventory_raw: Optional[Dict[str, Any]] = None
    media_raw: Optional[Dict[str, Any]] = None
    custom_fields: Optional[List[Dict[str, Any]]] = None

class ProductResponseSchema(ProductBaseSchema, SoftDeleteMixinSchema):
    id: UUID
    model_config = ConfigDict(from_attributes=True)