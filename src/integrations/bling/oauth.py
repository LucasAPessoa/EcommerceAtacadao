"""Fluxo OAuth (Authorization Code) do Bling: URL de autorização, troca do código e empresa.

Nenhuma mensagem de erro ou log contém código, token ou segredo.
"""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from src.core.client_config import BlingCredentials, get_client_config
from src.core.config import settings
from src.integrations.bling.errors import (
    BlingError,
    BlingRateLimitedError,
    BlingRejectedError,
    BlingUnavailableError,
)

HTTP_TIMEOUT_SECONDS = 15.0
# [a validar] endpoint dos dados da empresa e campo identificador estável (research R7).
COMPANY_PATH = "/empresas/me/dados-basicos"


@dataclass(frozen=True)
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int


@dataclass(frozen=True)
class CompanyInfo:
    id: str
    name: str


def _bling() -> BlingCredentials:
    bling = get_client_config().bling
    if bling is None:
        raise BlingError("Integração com o Bling não configurada.")
    return bling


def _basic_auth() -> tuple[str, str]:
    bling = _bling()
    return bling.client_id, bling.client_secret.get_secret_value()


def build_authorize_url(state: str) -> str:
    query = urlencode({"response_type": "code", "client_id": _bling().client_id, "state": state})
    return f"{settings.BLING_AUTH_BASE_URL.rstrip('/')}/oauth/authorize?{query}"


def parse_error_details(response: httpx.Response) -> tuple[str | None, str]:
    """Extrai tipo/mensagem do corpo de erro, sem repassar nada além desses campos."""
    try:
        body = response.json()
    except ValueError:
        return None, ""
    if not isinstance(body, dict):
        return None, ""
    err = body.get("error")
    if isinstance(err, dict):
        message = str(err.get("message") or "")[:200]
        fields = err.get("fields")
        if isinstance(fields, list):
            msgs = [str(f["msg"])[:120] for f in fields if isinstance(f, dict) and f.get("msg")]
            if msgs:
                message = f"{message}: {'; '.join(msgs[:5])}" if message else "; ".join(msgs[:5])
        return str(err.get("type") or "")[:80] or None, message
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
    error_type, message = parse_error_details(response)
    raise BlingRejectedError(status, error_type, message)


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise BlingUnavailableError() from None
    _raise_for_status(response)
    return response


async def _token_request(data: dict[str, str], fallback_refresh: str | None = None) -> TokenSet:
    response = await _send(
        "POST",
        f"{settings.BLING_AUTH_BASE_URL.rstrip('/')}/oauth/token",
        auth=_basic_auth(),
        headers={"Accept": "application/json"},
        data=data,
    )
    try:
        body = response.json()
        # Refresh rotativo: usa o novo se vier; senão mantém o anterior.
        refresh = body.get("refresh_token") or fallback_refresh
        return TokenSet(
            access_token=str(body["access_token"]),
            refresh_token=str(refresh),
            expires_in=int(body["expires_in"]),
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        raise BlingUnavailableError("Resposta de token do Bling inválida.") from None


async def exchange_code(code: str) -> TokenSet:
    """Troca o código de autorização por tokens (Basic auth + form-urlencoded)."""
    return await _token_request({"grant_type": "authorization_code", "code": code})


async def refresh_tokens(refresh_token: str) -> TokenSet:
    """Renova o access token. 400/401 chegam como ``BlingRejectedError`` (definitivo)."""
    return await _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        fallback_refresh=refresh_token,
    )


async def revoke_token(token: str) -> None:
    """Revoga no Bling (melhor esforço): nunca levanta."""
    try:
        await _send(
            "POST",
            f"{settings.BLING_AUTH_BASE_URL.rstrip('/')}/oauth/revoke",
            auth=_basic_auth(),
            data={"token": token},
        )
    except BlingError:
        pass


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
