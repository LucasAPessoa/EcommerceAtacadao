from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.integrations.bling_connection_repository import BlingConnectionRepository
from src.schemas.response_schema import BaseResponse
from src.services.integrations.bling_connection_service import (
    BlingAlreadyConnectedError,
    BlingConnectionService,
    BlingNotConfiguredError,
)

router = APIRouter(prefix="/integrations/bling", tags=["Bling"])

NOT_CONFIGURED_DETAIL = "Integração com o Bling não configurada."


class BlingConnectResponse(BaseModel):
    authorize_url: str


def get_bling_connection_service(
    session: AsyncSession = Depends(get_db),
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
