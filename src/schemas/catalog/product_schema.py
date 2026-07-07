from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

# ==========================================
# Schema Base: Campos comunes a todas las operaciones
# ==========================================
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

# ==========================================
# Schema Create: Usado no POST
# ==========================================
class ProductCreateSchema(ProductBaseSchema):
    # O 'name' já é obrigatório no ProductBase.
    # Se precisar que o 'code' (SKU) seja obrigatório na criação,
    # tu podes reescrever o campo aqui:
    # code: str = Field(..., max_length=100)
    pass

# ==========================================
# Schema Update: Usado no PATCH/PUT
# ==========================================
class ProductUpdateSchema(ProductBaseSchema):
    # Todos os campos viram opcionais para permitir updates parciais (PATCH)
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

# ==========================================
# Schema Response: Usado no retorno da API
# ==========================================
class ProductResponseSchema(ProductBaseSchema):
    id: UUID
    
    # Supondo que teus mixins TimestampMixin e SoftDeleteMixin gerem esses campos:
    created_at: datetime
    updated_at: datetime

    # Configuração do Pydantic V2 para ler objetos do SQLAlchemy (antigo orm_mode=True)
    model_config = ConfigDict(from_attributes=True)