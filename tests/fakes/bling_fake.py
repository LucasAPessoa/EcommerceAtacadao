"""Bling simulado para testes (ASGI). Uso: ``uvicorn tests.fakes.bling_fake:app --port N``.

Rotas do Bling sob ``/Api/v3`` (authorize, oauth/token, oauth/revoke, dados da empresa e um
recurso genérico) e rotas de controle sob ``/__control`` (configurar respostas, ler o
contador de chamadas, resetar). Nunca registra código, token nem segredo: as chamadas
guardam só método, caminho, ``grant_type`` e se o Basic auth estava correto.
"""

import base64
import itertools
import os
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(title="Bling simulado")

DEFAULT_CONFIG: dict[str, Any] = {
    # Modo por endpoint: success | invalid_grant | 400 | 429 | 503
    "token_mode": "success",
    "company_mode": "success",
    "resource_mode": "success",
    "revoke_mode": "success",
    "rotate_refresh": True,
    "expires_in": 3600,
    "company": {"id": "company-a", "nome": "Empresa A Ltda", "cnpj": "11222333000181"},
}

_config: dict[str, Any] = {}
_calls: list[dict[str, Any]] = []
_counter = itertools.count(1)


def _reset() -> None:
    _config.clear()
    _config.update({**DEFAULT_CONFIG, "company": dict(DEFAULT_CONFIG["company"])})
    _calls.clear()


_reset()


def _basic_ok(request: Request) -> bool:
    pair = f"{os.environ.get('BLING_CLIENT_ID', '')}:{os.environ.get('BLING_CLIENT_SECRET', '')}"
    expected = base64.b64encode(pair.encode()).decode()
    return request.headers.get("authorization", "") == f"Basic {expected}"


def _failure(mode: str) -> JSONResponse | None:
    if mode == "success":
        return None
    if mode == "invalid_grant":
        return JSONResponse(
            {"error": {"type": "invalid_grant", "message": "Invalid grant"}}, status_code=400
        )
    status = int(mode)
    return JSONResponse(
        {"error": {"type": "simulated", "message": f"Simulated {status}"}}, status_code=status
    )


@app.get("/Api/v3/oauth/authorize")
async def authorize(client_id: str, state: str = "", response_type: str = "code"):
    _calls.append({"method": "GET", "path": "/oauth/authorize"})
    # Simula o usuário aprovando: o redirecionamento real é decidido pelo app Bling.
    return RedirectResponse("/__control/authorized?" + urlencode({"state": state}))


@app.post("/Api/v3/oauth/token")
async def token(request: Request):
    form = await request.form()
    grant = str(form.get("grant_type", ""))
    _calls.append(
        {
            "method": "POST",
            "path": "/oauth/token",
            "grant_type": grant,
            "basic_ok": _basic_ok(request),
        }
    )
    if not _basic_ok(request):
        return JSONResponse({"error": {"type": "invalid_client", "message": "bad client"}}, 401)
    if grant not in ("authorization_code", "refresh_token"):
        return JSONResponse({"error": {"type": "unsupported_grant_type", "message": ""}}, 400)
    if failure := _failure(_config["token_mode"]):
        return failure
    n = next(_counter)
    refresh = f"refresh-{n}" if _config["rotate_refresh"] else "refresh-static"
    return {
        "access_token": f"access-{n}",
        "refresh_token": refresh,
        "expires_in": _config["expires_in"],
        "token_type": "Bearer",
    }


@app.post("/Api/v3/oauth/revoke")
async def revoke(request: Request):
    _calls.append({"method": "POST", "path": "/oauth/revoke", "basic_ok": _basic_ok(request)})
    if failure := _failure(_config["revoke_mode"]):
        return failure
    return JSONResponse({}, status_code=200)


@app.get("/Api/v3/empresas/me/dados-basicos")
async def company(request: Request):
    _calls.append({"method": "GET", "path": "/empresas/me/dados-basicos"})
    if not request.headers.get("authorization", "").startswith("Bearer access-"):
        return JSONResponse({"error": {"type": "invalid_token", "message": "unauthorized"}}, 401)
    if failure := _failure(_config["company_mode"]):
        return failure
    return {"data": _config["company"]}


@app.api_route("/Api/v3/recursos/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def resource(rest: str, request: Request):
    _calls.append({"method": request.method, "path": f"/recursos/{rest}"})
    if not request.headers.get("authorization", "").startswith("Bearer access-"):
        return JSONResponse({"error": {"type": "invalid_token", "message": "unauthorized"}}, 401)
    if failure := _failure(_config["resource_mode"]):
        return failure
    return {"data": {"path": rest}}


@app.get("/__control/authorized", include_in_schema=False)
async def authorized():
    return {"authorized": True}


@app.post("/__control/config")
async def set_config(request: Request):
    _config.update(await request.json())
    return {"ok": True}


@app.post("/__control/reset")
async def reset():
    _reset()
    return {"ok": True}


@app.get("/__control/calls")
async def calls():
    return _calls


@app.get("/health")
async def health():
    return {"status": "ok"}
