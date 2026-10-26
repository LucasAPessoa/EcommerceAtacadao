from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.core.client_config import get_client_config
from src.core.config import settings
from src.core.db import AsyncSessionLocal, DbSession
from src.core.sec import require_role
from src.models.enums import CatalogSyncTriggerEnum
from src.models.identity import User
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
from src.repositories.integrations.bling_connection_repository import BlingConnectionRepository
from src.schemas.integrations.bling_schema import BlingStatusResponse
from src.schemas.integrations.catalog_sync_schema import (
    CatalogSyncCurrentRunSchema,
    CatalogSyncRunsResponse,
)
from src.schemas.response_schema import BaseResponse
from src.services.catalog.catalog_sync_service import CatalogSyncService, build_catalog_client
from src.services.integrations.bling_connection_service import (
    BlingAlreadyConnectedError,
    BlingAlreadyDisconnectedError,
    BlingConnectionService,
    BlingNotConfiguredError,
)

router = APIRouter(prefix="/integrations/bling", tags=["Bling"])

NOT_CONFIGURED_DETAIL = "Integração com o Bling não configurada."
# O disparo manual roda dentro da requisição do admin: fatia curta; o cron continua o ciclo.
MANUAL_SLICE_BUDGET_SECONDS = 20.0


class BlingConnectResponse(BaseModel):
    authorize_url: str


def get_bling_connection_service(
    session: DbSession,
) -> BlingConnectionService:
    return BlingConnectionService(BlingConnectionRepository(session))


@router.post("/connect", response_model=BaseResponse[BlingConnectResponse])
async def connect_bling(
    current_user: User = Depends(require_role(["admin"])),
    service: BlingConnectionService = Depends(get_bling_connection_service),
):
    """Inicia a conexão: cria a tentativa e devolve a URL de autorização do Bling."""
    try:
        url = await service.start_connect(current_user.id)
    except BlingNotConfiguredError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_CONFIGURED_DETAIL)
    except BlingAlreadyConnectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    return BaseResponse(status="success", data=BlingConnectResponse(authorize_url=url))


@router.get("/callback", include_in_schema=False)
async def bling_callback(
    code: Optional[str] = Query(default=None, max_length=2048),
    state: Optional[str] = Query(default=None, max_length=2048),
    error: Optional[str] = Query(default=None, max_length=200),
    service: BlingConnectionService = Depends(get_bling_connection_service),
):
    """Retorno do Bling (via redirecionador central): sempre 302 para o front."""
    try:
        result = await service.handle_callback(code, state, error)
    except BlingNotConfiguredError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_CONFIGURED_DETAIL)
    return RedirectResponse(service.result_url(result), status_code=status.HTTP_302_FOUND)


@router.get("/status", response_model=BaseResponse[BlingStatusResponse])
async def bling_status(
    current_user: User = Depends(require_role(["admin"])),
    service: BlingConnectionService = Depends(get_bling_connection_service),
):
    """Estado da conexão (sem tokens), com os 10 eventos mais recentes."""
    return BaseResponse(status="success", data=await service.get_status())


@router.post("/disconnect", response_model=BaseResponse[BlingStatusResponse])
async def disconnect_bling(
    current_user: User = Depends(require_role(["admin"])),
    service: BlingConnectionService = Depends(get_bling_connection_service),
):
    """Revoga no Bling (melhor esforço), apaga os tokens e mantém a empresa vinculada."""
    try:
        data = await service.disconnect(current_user.id)
    except BlingAlreadyDisconnectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    return BaseResponse(status="success", data=data)


def get_catalog_sync_service(session: DbSession) -> CatalogSyncService:
    # O cliente do Bling usa sessões curtas próprias para o token (sem tocar nesta sessão).
    return CatalogSyncService(
        CatalogSyncRepository(session),
        build_catalog_client(AsyncSessionLocal),
        budget_seconds=min(settings.CATALOG_SYNC_TIME_BUDGET_SECONDS, MANUAL_SLICE_BUDGET_SECONDS),
    )


@router.post("/catalog-sync", response_model=BaseResponse[CatalogSyncCurrentRunSchema])
async def start_catalog_sync(
    current_user: User = Depends(require_role(["admin"])),
    service: CatalogSyncService = Depends(get_catalog_sync_service),
):
    """Pede um ciclo e executa uma fatia; se já há ciclo em andamento, devolve-o."""
    if not get_client_config().bling_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_CONFIGURED_DETAIL)
    result = await service.run_job(CatalogSyncTriggerEnum.MANUAL, current_user.id, force=True)
    if result.status == "SKIPPED":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Conexão com o Bling inativa")
    data = await service.get_run_schema(result.run_id) if result.run_id else None
    if data is None:  # outra invocação detém o estado: devolve o ciclo corrente
        data = (await service.list_runs(1)).current
    if data is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Importação já em andamento")
    return BaseResponse(status="success", data=data)


@router.get("/catalog-sync/runs", response_model=BaseResponse[CatalogSyncRunsResponse])
async def list_catalog_sync_runs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(["admin"])),
    service: CatalogSyncService = Depends(get_catalog_sync_service),
):
    """Ciclo corrente e histórico recente (no máximo 50 erros por execução; sem tokens)."""
    return BaseResponse(status="success", data=await service.list_runs(limit))
