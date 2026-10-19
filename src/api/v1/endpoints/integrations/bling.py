from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.core.db import DbSession
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.integrations.bling_connection_repository import BlingConnectionRepository
from src.schemas.integrations.bling_schema import BlingStatusResponse
from src.schemas.response_schema import BaseResponse
from src.services.integrations.bling_connection_service import (
    BlingAlreadyConnectedError,
    BlingAlreadyDisconnectedError,
    BlingConnectionService,
    BlingNotConfiguredError,
)

router = APIRouter(prefix="/integrations/bling", tags=["Bling"])

NOT_CONFIGURED_DETAIL = "Integração com o Bling não configurada."


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
