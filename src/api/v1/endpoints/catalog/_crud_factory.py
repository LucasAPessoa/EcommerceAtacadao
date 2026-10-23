"""
Fábrica genérica de rotas CRUD para o módulo catalog.

Os 9+ endpoints de catálogo (product, category, pricing-tiers, listing-images,
listing-attributes, product-images, product-listings, product-questions,
product-reviews, product-variants) eram cópias quase idênticas do mesmo
boilerplate: injeção de sessão/serviço, POST/GET/GET-by-id/PATCH/DELETE,
BaseResponse. Isso fazia bug e correção divergirem entre eles (ex.: alguns
capturavam ValueError e devolviam 400, outros não; nenhum tinha autenticação).

Esta fábrica concentra o padrão em um único lugar:
- POST/PATCH/DELETE exigem autenticação (e, opcionalmente, uma role específica).
- GET/GET-by-id continuam públicos (navegação do catálogo é pública num e-commerce).
- ValueError levantado pelo service vira 400 de forma consistente em create/update.
- 404 padronizado quando o registro não existe.

Cada router de entidade agora é só uma chamada a build_crud_router() passando
os nomes dos métodos do service (o "verbs"), porque os services não têm uma
nomenclatura 100% padronizada (create_tier, create_attribute, create_image...).
"""

from typing import Callable, List, Optional, Type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.core.sec import get_current_active_user, get_optional_current_user, require_role
from src.schemas.response_schema import BaseResponse


def build_crud_router(
    *,
    prefix: str,
    tags: List[str],
    service_dependency: Callable,
    create_schema: Optional[Type[BaseModel]] = None,
    update_schema: Optional[Type[BaseModel]] = None,
    response_schema: Type[BaseModel],
    verbs: dict,
    not_found_message: str = "Registro não encontrado.",
    supports_pagination: bool = False,
    create_roles: Optional[List[str]] = None,
    write_roles: Optional[List[str]] = None,
    create_as_author: bool = False,
    hide_unapproved_from_public: bool = False,
    read_only: bool = False,
) -> APIRouter:
    """
    verbs: dict com os nomes reais dos métodos do service, ex.:
        {"create": "create_tier", "list": "list_tiers", "get": "get_tier_by_id",
        "update": "update_tier", "delete": "delete_tier"}

    create_roles / write_roles: lista de roles (ex. ["admin"]) exigidas para
        criar / para atualizar+excluir. Se None, basta estar autenticado e
        ativo (get_current_active_user), sem checar role específica.

    create_as_author: se True, o service de criação recebe o id do usuário
        autenticado como 2º argumento (autor definido pelo servidor, nunca
        pelo payload).

    hide_unapproved_from_public: se True, GET de lista/por id usam auth
        opcional e passam `include_unapproved=<é admin>` ao service. Anônimo,
        token inválido ou role não-admin só veem registros aprovados (o
        por-id de não aprovado vira 404). Token inválido NÃO gera 401.

    read_only: se True, não registra POST/PATCH/DELETE (só GETs); o roteamento
        responde 405 a essas operações. Nesse caso create_schema, update_schema
        e os verbs "create"/"update"/"delete" são dispensáveis.
    """
    router = APIRouter(prefix=prefix, tags=tags)  # type: ignore[arg-type]  # list[str] aceito pelo FastAPI (tags: list[str | Enum])

    def _create_dependency():
        if create_roles:
            return Depends(require_role(create_roles))
        return Depends(get_current_active_user)

    def _write_dependency():
        if write_roles:
            return Depends(require_role(write_roles))
        return Depends(get_current_active_user)

    if not read_only:

        @router.post(
            "/",
            response_model=BaseResponse[response_schema],  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
            status_code=status.HTTP_201_CREATED,
        )
        async def create_item(
            payload: create_schema,  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
            service=Depends(service_dependency),
            _user=_create_dependency(),
        ):
            try:
                create = getattr(service, verbs["create"])
                data = await (create(payload, _user.id) if create_as_author else create(payload))
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            return BaseResponse(status="success", data=data)

    async def _no_viewer():
        return None

    # Só resolve o usuário opcional quando o recurso filtra por role.
    _viewer_dependency = get_optional_current_user if hide_unapproved_from_public else _no_viewer

    def _read_kwargs(user) -> dict:
        if not hide_unapproved_from_public:
            return {}
        is_admin = bool(user and user.role and user.role.name == "admin")
        return {"include_unapproved": is_admin}

    if supports_pagination:

        @router.get("/", response_model=BaseResponse[List[response_schema]])  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
        async def list_items(
            skip: int = 0,
            limit: int = 100,
            service=Depends(service_dependency),
            viewer=Depends(_viewer_dependency),
        ):
            data = await getattr(service, verbs["list"])(
                skip=skip, limit=limit, **_read_kwargs(viewer)
            )
            return BaseResponse(status="success", data=data)
    else:

        @router.get("/", response_model=BaseResponse[List[response_schema]])  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
        async def list_items(  # type: ignore[misc]  # mesma rota definida em ramos if/else exclusivos
            service=Depends(service_dependency),
            viewer=Depends(_viewer_dependency),
        ):
            data = await getattr(service, verbs["list"])(**_read_kwargs(viewer))
            return BaseResponse(status="success", data=data)

    @router.get("/{item_id}", response_model=BaseResponse[response_schema])  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
    async def get_item(
        item_id: UUID,
        service=Depends(service_dependency),
        viewer=Depends(_viewer_dependency),
    ):
        data = await getattr(service, verbs["get"])(item_id, **_read_kwargs(viewer))
        if not data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)
        return BaseResponse(status="success", data=data)

    if not read_only:

        @router.patch("/{item_id}", response_model=BaseResponse[response_schema])  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
        async def update_item(
            item_id: UUID,
            payload: update_schema,  # type: ignore[valid-type]  # schema dinâmico: FastAPI resolve a anotação em runtime
            service=Depends(service_dependency),
            _user=_write_dependency(),
        ):
            try:
                data = await getattr(service, verbs["update"])(item_id, payload)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            if not data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)
            return BaseResponse(status="success", data=data)

        @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
        async def delete_item(
            item_id: UUID,
            service=Depends(service_dependency),
            _user=_write_dependency(),
        ):
            success = await getattr(service, verbs["delete"])(item_id)
            if not success:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)

    return router
