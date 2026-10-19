"""Fluxo OAuth (Authorization Code) do Bling: URL de autorização, troca do código e empresa.

Nenhuma mensagem de erro ou log contém código, token ou segredo.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from src.core.config import settings
from src.integrations.bling.errors import (
    BlingRateLimitedError,
    BlingRejectedError,
    BlingUnavailableError,
)

HTTP_TIMEOUT_SECONDS = 15.0
# [a validar] endpoint dos dados da empresa e campo identificador estável (research R7).
COMPANY_PATH = "/empresas/me/dados-basicos"


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class CompanyInfo:
    id: str
    name: str


def build_authorize_url(state: str) -> str:
    query = urlencode(
        {"response_type": "code", "client_id": settings.BLING_CLIENT_ID, "state": state}
    )
    return f"{settings.BLING_AUTH_BASE_URL.rstrip('/')}/oauth/authorize?{query}"


def _error_details(response: httpx.Response) -> tuple[str | None, str]:
    """Extrai tipo/mensagem do corpo de erro, sem repassar nada além desses campos."""
    try:
        body = response.json()
    except ValueError:
        return None, ""
    if not isinstance(body, dict):
        return None, ""
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("type") or "")[:80] or None, str(err.get("message") or "")[:200]
    if isinstance(err, str):
        return err[:80], str(body.get("error_description") or "")[:200]
    return None, ""


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    if status == 429:
        raise BlingRateLimitedError()
    if status >= 500:
        raise BlingUnavailableError()
    error_type, message = _error_details(response)
    raise BlingRejectedError(status, error_type, message)


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise BlingUnavailableError() from None
    _raise_for_status(response)
    return response


async def exchange_code(code: str) -> TokenSet:
    """Troca o código de autorização por tokens (Basic auth + form-urlencoded)."""
    response = await _send(
        "POST",
        f"{settings.BLING_AUTH_BASE_URL.rstrip('/')}/oauth/token",
        auth=(settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "authorization_code", "code": code},
    )
    try:
        body = response.json()
        return TokenSet(
            access_token=str(body["access_token"]),
            refresh_token=str(body["refresh_token"]),
            expires_in=int(body["expires_in"]),
        )
    except (ValueError, KeyError, TypeError):
        raise BlingUnavailableError("Resposta de token do Bling inválida.") from None


async def fetch_company(access_token: str) -> CompanyInfo:
    """Consulta a empresa da conta autorizada. Isolada: o endpoint real é [a validar]."""
    response = await _send(
        "GET",
        f"{settings.BLING_API_BASE_URL.rstrip('/')}{COMPANY_PATH}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        data = response.json()["data"]
        company_id = str(data.get("id") or data["cnpj"])
        name = str(data.get("nome") or data.get("fantasia") or "")[:200]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise BlingUnavailableError("Resposta de empresa do Bling inválida.") from None
    return CompanyInfo(id=company_id[:64], name=name)
