"""Redirecionador central do OAuth do Bling (sem banco, sem Settings da loja, sem Bling).

Recebe ``/bling/callback`` do Bling, valida o ``state`` assinado e responde 302 para o
``callback_url`` do tenant correspondente. Nunca redireciona para fora de ``PLATFORM_TENANTS``.
"""

import json
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from src.integrations.bling.state import StateError, peek_tenant, verify_state

logger = logging.getLogger("platform_router")

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_INVALID_HTML = (
    "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
    "<title>Link inválido</title></head><body><p>Link de autorização inválido; "
    "inicie a conexão novamente pelo painel da loja.</p></body></html>"
)


class RouterConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantRoute:
    callback_url: str
    state_key: str


def load_tenants(raw: str | None = None) -> dict[str, TenantRoute]:
    raw = os.environ.get("PLATFORM_TENANTS") if raw is None else raw
    if not raw or not raw.strip():
        raise RouterConfigError("PLATFORM_TENANTS ausente: defina o JSON de tenants.")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RouterConfigError("PLATFORM_TENANTS não é um JSON válido.") from exc
    if not isinstance(data, dict) or not data:
        raise RouterConfigError("PLATFORM_TENANTS deve ser um objeto JSON não vazio.")
    tenants: dict[str, TenantRoute] = {}
    for tenant_id, entry in data.items():
        if not isinstance(entry, dict):
            raise RouterConfigError(f"PLATFORM_TENANTS: tenant '{tenant_id}' inválido.")
        url, key = entry.get("callback_url"), entry.get("state_key")
        if not isinstance(url, str) or not isinstance(key, str) or not url or not key:
            raise RouterConfigError(
                f"PLATFORM_TENANTS: tenant '{tenant_id}' precisa de callback_url e state_key."
            )
        parts = urlsplit(url)
        local_http = parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
        if (
            not parts.hostname
            or not (parts.scheme == "https" or local_http)
            or parts.fragment
            or parts.username
            or parts.password
        ):
            raise RouterConfigError(
                f"PLATFORM_TENANTS: callback_url do tenant '{tenant_id}' deve ser https,"
                " sem fragmento nem credenciais."
            )
        tenants[tenant_id] = TenantRoute(callback_url=url, state_key=key)
    return tenants


def _invalid() -> HTMLResponse:
    return HTMLResponse(_INVALID_HTML, status_code=400)


def create_app(tenants: dict[str, TenantRoute] | None = None) -> FastAPI:
    routes = load_tenants() if tenants is None else tenants
    app = FastAPI(title="Platform router", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/bling/callback")
    async def bling_callback(
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
    ) -> Response:
        if not state:
            logger.warning("bling callback recusado: reason=missing_state")
            return _invalid()
        try:
            tenant_id = peek_tenant(state)
        except StateError as exc:
            logger.warning("bling callback recusado: reason=%s", exc.reason)
            return _invalid()
        route = routes.get(tenant_id)
        if route is None:
            # tenant vem de um state ainda não assinado: logar truncado e escapado
            logger.warning(
                "bling callback recusado: tenant=%r reason=unknown_tenant", tenant_id[:64]
            )
            return _invalid()
        try:
            verify_state(state, route.state_key, expected_tenant=tenant_id)
        except StateError as exc:
            logger.warning(
                "bling callback recusado: tenant=%r reason=%s", tenant_id[:64], exc.reason
            )
            return _invalid()
        if not error and not code:
            logger.warning("bling callback recusado: tenant=%s reason=missing_code", tenant_id)
            return _invalid()
        params = {"error": error} if error else {"code": code or ""}
        if not error and code is None:
            params = {}
        params["state"] = state
        separator = "&" if urlsplit(route.callback_url).query else "?"
        location = f"{route.callback_url}{separator}{urlencode(params)}"
        logger.info("bling callback encaminhado: tenant=%s", tenant_id)
        return RedirectResponse(location, status_code=302)

    return app
