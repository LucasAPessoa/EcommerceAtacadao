import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_primary_key
from .enums import BlingConnectionEventEnum, BlingConnectionStatusEnum


class BlingConnection(Base, TimestampMixin):
    """Conexão da conta Bling da loja. No máximo uma linha por banco."""

    __tablename__ = "bling_connections"
    __table_args__ = (
        # Singleton: a coluna só aceita TRUE e é única, logo existe no máximo uma linha.
        CheckConstraint("singleton", name="ck_bling_connections_singleton"),
        UniqueConstraint("singleton", name="uq_bling_connections_singleton"),
    )

    id: Mapped[uuid.UUID] = uuid_primary_key()
    singleton: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[BlingConnectionStatusEnum] = mapped_column(
        SQLEnum(BlingConnectionStatusEnum), default=BlingConnectionStatusEnum.NOT_CONNECTED
    )
    company_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    access_token_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    refresh_token_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    access_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refresh_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class BlingAuthorizationAttempt(Base):
    """Tentativa de autorização OAuth (state de uso único, guardado só como hash)."""

    __tablename__ = "bling_authorization_attempts"

    id: Mapped[uuid.UUID] = uuid_primary_key()
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    initiated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BlingConnectionEvent(Base):
    """Auditoria da conexão: sem tokens nem dados pessoais."""

    __tablename__ = "bling_connection_events"

    id: Mapped[uuid.UUID] = uuid_primary_key()
    event: Mapped[BlingConnectionEventEnum] = mapped_column(SQLEnum(BlingConnectionEventEnum))
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
