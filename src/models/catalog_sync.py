import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, uuid_primary_key
from .enums import CatalogSyncPhaseEnum, CatalogSyncRunStatusEnum, CatalogSyncTriggerEnum


class CatalogSyncRun(Base):
    """Execução (ciclo) da importação do catálogo do Bling. Retenção: últimas 200."""

    __tablename__ = "catalog_sync_runs"

    id: Mapped[uuid.UUID] = uuid_primary_key()
    trigger: Mapped[CatalogSyncTriggerEnum] = mapped_column(SQLEnum(CatalogSyncTriggerEnum))
    triggered_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[CatalogSyncRunStatusEnum] = mapped_column(
        SQLEnum(CatalogSyncRunStatusEnum), default=CatalogSyncRunStatusEnum.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invocations: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deactivated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Lista de {bling_id, code, message}; no máximo 200 itens, sem dados sensíveis.
    errors: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class CatalogSyncState(Base):
    """Estado do ciclo corrente. No máximo uma linha (id = 1)."""

    __tablename__ = "catalog_sync_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_catalog_sync_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    current_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog_sync_runs.id"), nullable=True
    )
    phase: Mapped[CatalogSyncPhaseEnum] = mapped_column(
        SQLEnum(CatalogSyncPhaseEnum),
        default=CatalogSyncPhaseEnum.IDLE,
        server_default=CatalogSyncPhaseEnum.IDLE.value,
    )
    cursor: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    seen_bling_ids: Mapped[List[int]] = mapped_column(JSONB, default=list, server_default="[]")
    changed_bling_ids: Mapped[List[int]] = mapped_column(JSONB, default=list, server_default="[]")
    scan_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_complete_cycle_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_full_detail_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requested_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
