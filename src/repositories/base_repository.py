import uuid
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# Importe a sua Base e o SoftDeleteMixin
from src.models.base import Base, SoftDeleteMixin

# Define um tipo genérico que deve herdar da Base do SQLAlchemy
ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[ModelType]:
        """Busca um registo pelo ID, ignorando os que sofreram soft delete."""
        query = select(self.model).where(self.model.id == id)
        
        # Injeção automática do filtro de Soft Delete
        if issubclass(self.model, SoftDeleteMixin):
            query = query.where(self.model.deleted_at.is_(None))
            
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Retorna uma lista de registos ativos (não apagados)."""
        query = select(self.model)
        
        if issubclass(self.model, SoftDeleteMixin):
            query = query.where(self.model.deleted_at.is_(None))
            
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, obj_in: Dict[str, Any]) -> ModelType:
        """Cria e guarda um novo registo no banco."""
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush() # Retorna o ID gerado (UUID) sem fechar a transação
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: Dict[str, Any]) -> ModelType:
        """Atualiza os campos de um registo existente."""
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Executa um Soft Delete se o modelo o suportar.
        Caso contrário, você pode implementar um hard delete ou lançar uma exceção.
        """
        if issubclass(self.model, SoftDeleteMixin):
            query = (
                update(self.model)
                .where(self.model.id == id, self.model.deleted_at.is_(None))
                .values(deleted_at=datetime.utcnow())
            )
            result = await self.session.execute(query)
            return result.rowcount > 0
        
        
        raise NotImplementedError("Este modelo não suporta exclusão.")