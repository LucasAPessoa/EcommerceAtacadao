"""Bling simulado para testes (ASGI). Uso: ``uvicorn tests.fakes.bling_fake:app --port N``.

Rotas do Bling sob ``/Api/v3`` (authorize, oauth/token, oauth/revoke, dados da empresa,
catálogo de leitura e um recurso genérico) e rotas de controle sob ``/__control`` (configurar
respostas, ler o contador de chamadas, resetar). Nunca registra código, token nem segredo:
as chamadas guardam só método, caminho, ``grant_type`` e se o Basic auth estava correto.
"""

import base64
import copy
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
    # Catálogo: "products" (detalhes no formato do Bling), "categories", "balances"
    # ({"<id>": saldo}) e "catalog_failures" ({"produtos:list:2": 503, "produtos:detail:7": 429,
    # "categorias:1": 503, "saldos": 503}).
    "products": [],
    "categories": [],
    "balances": {},
    "catalog_failures": {},
    # Imagens como links S3 assinados do Bling real: Signature/Expires mudam a cada leitura.
    "sign_images": False,
}

_config: dict[str, Any] = {}
_calls: list[dict[str, Any]] = []
_counter = itertools.count(1)


def _reset() -> None:
    _config.clear()
    _config.update(copy.deepcopy(DEFAULT_CONFIG))
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


def _catalog_guard(request: Request, key: str) -> JSONResponse | None:
    _calls.append({"method": "GET", "path": f"/catalogo/{key}"})
    if not request.headers.get("authorization", "").startswith("Bearer access-"):
        return JSONResponse({"error": {"type": "invalid_token", "message": "unauthorized"}}, 401)
    failure = _config["catalog_failures"].get(key)
    return _failure(str(failure)) if failure else None


def _paginate(rows: list[Any], pagina: int, limite: int) -> list[Any]:
    start = (max(pagina, 1) - 1) * limite
    return rows[start : start + limite]


@app.get("/Api/v3/produtos")
async def list_products(
    request: Request,
    pagina: int = 1,
    limite: int = 100,
    dataAlteracaoInicial: str | None = None,
    situacao: str | None = None,
):
    if failure := _catalog_guard(request, f"produtos:list:{pagina}"):
        return failure
    rows = []
    for product in _config["products"]:
        changed = product.get("dataAlteracao")
        if dataAlteracaoInicial and not (changed and changed >= dataAlteracaoInicial):
            continue
        if situacao and product.get("situacao", "A") != situacao:
            continue
        rows.append(
            {
                "id": product["id"],
                "nome": product.get("nome"),
                "codigo": product.get("codigo"),
                "situacao": product.get("situacao", "A"),
                "formato": product.get("formato", "S"),
                "dataAlteracao": changed,
            }
        )
    return {"data": _paginate(rows, pagina, limite)}


def _signed(product: dict[str, Any]) -> dict[str, Any]:
    """Cópia do detalhe com cada link de imagem assinado de novo (como o S3 do Bling)."""
    signed = copy.deepcopy(product)
    nodes = [signed, *(v for v in signed.get("variacoes") or [] if isinstance(v, dict))]
    for node in nodes:
        images = ((node.get("midia") or {}).get("imagens")) or {}
        for group in ("externas", "internas"):
            for entry in images.get(group) or []:
                n = next(_counter)
                entry["link"] = (
                    f"{entry['link'].split('?', 1)[0]}?AWSAccessKeyId=AKIAFAKE"
                    f"&Expires={1_800_000_000 + n}&Signature=sig{n}"
                )
    return signed


@app.get("/Api/v3/produtos/{product_id}")
async def get_product(request: Request, product_id: int):
    if failure := _catalog_guard(request, f"produtos:detail:{product_id}"):
        return failure
    for product in _config["products"]:
        if product["id"] == product_id:
            return {"data": _signed(product) if _config["sign_images"] else product}
    return JSONResponse({"error": {"type": "RESOURCE_NOT_FOUND", "message": "nf"}}, 404)


@app.get("/Api/v3/categorias/produtos")
async def list_categories(request: Request, pagina: int = 1, limite: int = 100):
    if failure := _catalog_guard(request, f"categorias:{pagina}"):
        return failure
    return {"data": _paginate(_config["categories"], pagina, limite)}


@app.get("/Api/v3/estoques/saldos")
async def balances(request: Request):
    if failure := _catalog_guard(request, "saldos"):
        return failure
    ids = request.query_params.getlist("idsProdutos[]")
    saldos = _config["balances"]
    return {
        "data": [
            {
                "produto": {"id": int(i)},
                "saldoFisicoTotal": saldos[i],
                "saldoVirtualTotal": saldos[i],
            }
            for i in ids
            if i in saldos
        ]
    }


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
