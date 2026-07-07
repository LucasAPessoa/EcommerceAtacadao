import uuid
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from pydantic import BaseModel

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# Importe a sua Base e o SoftDeleteMixin
from src.models.base import Base, SoftDeleteMixin

# Define os tipos genéricos: um para o Model do banco e outro para o Schema do Pydantic
ModelType = TypeVar("ModelType", bound=Base)
ResponseSchemaType = TypeVar("ResponseSchemaType", bound=BaseModel)

class BaseRepository(Generic[ModelType, ResponseSchemaType]):
    def __init__(self, model: Type[ModelType], response_schema: Type[ResponseSchemaType], session: AsyncSession):
        self.model = model
        self.response_schema = response_schema
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[ResponseSchemaType]:
        """Busca um registo pelo ID e retorna o Schema pronto, ignorando soft delete."""
        query = select(self.model).where(self.model.id == id)
        
        if issubclass(self.model, SoftDeleteMixin):
            query = query.where(self.model.deleted_at.is_(None))
            
        result = await self.session.execute(query)
        db_obj = result.scalar_one_or_none()
        
        # Se achou o cara no banco, valida e transforma em Schema antes de retornar, tá?
        if db_obj:
            return self.response_schema.model_validate(db_obj)
        return None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ResponseSchemaType]:
        """Retorna uma lista de Schemas ativos (não apagados)."""
        query = select(self.model)
        
        if issubclass(self.model, SoftDeleteMixin):
            query = query.where(self.model.deleted_at.is_(None))
            
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        db_objs = result.scalars().all()
        
        # Faz o list comprehension convertendo cada model para o seu respectivo Schema
        return [self.response_schema.model_validate(obj) for obj in db_objs]

    async def create(self, obj_in: Dict[str, Any]) -> ResponseSchemaType:
        """Cria, guarda no banco e retorna o Schema preenchido."""
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush() # Dá o flush para gerar o ID/Timestamps no banco
        
        return self.response_schema.model_validate(db_obj)

    async def update(self, id: uuid.UUID, obj_in: Dict[str, Any]) -> Optional[ResponseSchemaType]:
        """Busca o registro pelo ID, atualiza os campos e retorna o Schema atualizado."""
        # Precisamos buscar a instância do banco primeiro para fazer o tracking da alteração
        query = select(self.model).where(self.model.id == id)
        if issubclass(self.model, SoftDeleteMixin):
            query = query.where(self.model.deleted_at.is_(None))
            
        result = await self.session.execute(query)
        db_obj = result.scalar_one_or_none()
        
        if not db_obj:
            return None
            
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        self.session.add(db_obj)
        await self.session.flush()
        
        return self.response_schema.model_validate(db_obj)

    async def delete(self, id: uuid.UUID) -> bool:
        """Executa um Soft Delete se o modelo o suportar (Mantém o retorno booleano)."""
        if issubclass(self.model, SoftDeleteMixin):
            query = (
                update(self.model)
                .where(self.model.id == id, self.model.deleted_at.is_(None))
                .values(deleted_at=datetime.utcnow())
            )
            result = await self.session.execute(query)
            return result.rowcount > 0
        
        raise NotImplementedError("Este modelo não suporta exclusão.")