from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from src.models.catalog_sync import CatalogSyncRun
from src.models.enums import CatalogSyncPhaseEnum

MAX_ERRORS_IN_RESPONSE = 50


class CatalogSyncCountsSchema(BaseModel):
    created: int
    updated: int
    deactivated: int
    blocked: int
    unchanged: int
    failed: int


class CatalogSyncErrorSchema(BaseModel):
    bling_id: Optional[int] = None
    code: str
    message: str


class CatalogSyncRunSchema(BaseModel):
    """Execução da importação (sem tokens nem dados sensíveis)."""

    id: UUID
    trigger: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    counts: CatalogSyncCountsSchema
    errors: list[CatalogSyncErrorSchema]
    reason: Optional[str] = None

    @classmethod
    def from_run(cls, run: CatalogSyncRun) -> "CatalogSyncRunSchema":
        return cls(**cls._fields(run))

    @staticmethod
    def _fields(run: CatalogSyncRun) -> dict:
        return {
            "id": run.id,
            "trigger": run.trigger.value,
            "status": run.status.value,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "counts": CatalogSyncCountsSchema(
                created=run.created,
                updated=run.updated,
                deactivated=run.deactivated,
                blocked=run.blocked,
                unchanged=run.unchanged,
                failed=run.failed,
            ),
            "errors": [
                CatalogSyncErrorSchema(
                    bling_id=e.get("bling_id"), code=str(e["code"]), message=str(e["message"])
                )
                for e in (run.errors or [])[:MAX_ERRORS_IN_RESPONSE]
            ],
            "reason": run.reason,
        }


class CatalogSyncCurrentRunSchema(CatalogSyncRunSchema):
    """Execução corrente: acrescenta a fase (`phase` só existe aqui)."""

    phase: Optional[str] = None

    @classmethod
    def from_run(
        cls, run: CatalogSyncRun, phase: Optional[CatalogSyncPhaseEnum] = None
    ) -> "CatalogSyncCurrentRunSchema":
        return cls(**cls._fields(run), phase=phase.value if phase else None)


class CatalogSyncRunsResponse(BaseModel):
    current: Optional[CatalogSyncCurrentRunSchema] = None
    items: list[CatalogSyncRunSchema]


class CatalogSyncJobResponse(BaseModel):
    run_id: Optional[UUID] = None
    status: str
    phase: Optional[str] = None
    interrupted_by_budget: bool
