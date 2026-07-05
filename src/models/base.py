from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Classe base declarativa do SQLAlchemy 2.0 para todo o projeto."""
    pass


def uuid_primary_key() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class TimestampMixin:
    """Adiciona campos de controle de tempo a qualquer tabela (Auditoria)."""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SoftDeleteMixin:
    """Garante que registros não sejam apagados definitivamente (Soft Delete)."""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None