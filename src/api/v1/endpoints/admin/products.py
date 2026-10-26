import uuid
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.endpoints.admin._params import PageParams, page_params
from src.core.client_config import get_client_config
from src.core.db import DbSession
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.admin.admin_product_repository import (
    AdminProductRepository,
    ProductListFilters,
)
from src.repositories.admin.presentation_repository import PresentationRepository
from src.schemas.admin.presentation import (
    BatchPresentationRequest,
    BatchPresentationResult,
    PresentationUpdate,
)
from src.schemas.admin.products import (
    AdminPresentation,
    AdminProductDetail,
    AdminProductListItem,
)
from src.schemas.response_schema import BaseResponse, PageMeta
from src.services.admin.presentation_service import (
    PresentationCategoryNotFoundError,
    PresentationProductNotFoundError,
    PresentationService,
)
from src.services.admin.product_admin_service import (
    AdminProductNotFoundError,
    ProductAdminService,
)

router = APIRouter(prefix="/products", tags=["Admin - Products"])


class ProductSort(str, Enum):
    name = "name"
    price = "price"
    stock = "stock"
    updated_at = "updated_at"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


def get_product_admin_service(session: DbSession) -> ProductAdminService:
    repository = AdminProductRepository(
        session, low_stock_threshold=get_client_config().low_stock_threshold
    )
    return ProductAdminService(repository)


def get_presentation_service(session: DbSession) -> PresentationService:
    return PresentationService(session, PresentationRepository(session))


@router.get("", response_model=BaseResponse[list[AdminProductListItem]])
async def list_products(
    q: Optional[str] = Query(None, max_length=100),
    category_id: Optional[uuid.UUID] = None,
    active: Optional[bool] = None,
    visible: Optional[bool] = None,
    featured: Optional[bool] = None,
    low_stock: Optional[bool] = None,
    pending: Optional[bool] = None,
    customized: Optional[bool] = None,
    sort: ProductSort = ProductSort.name,
    order: SortOrder = SortOrder.asc,
    page: PageParams = Depends(page_params),
    service: ProductAdminService = Depends(get_product_admin_service),
):
    filters = ProductListFilters(
        q=q,
        category_id=category_id,
        active=active,
        visible=visible,
        featured=featured,
        low_stock=low_stock,
        pending=pending,
        customized=customized,
        sort=sort.value,
        order=order.value,
    )
    items, total = await service.list_products(filters, page.skip, page.limit)
    return BaseResponse(data=items, meta=PageMeta(total=total, skip=page.skip, limit=page.limit))


@router.get("/{product_id}", response_model=BaseResponse[AdminProductDetail])
async def get_product(
    product_id: uuid.UUID,
    service: ProductAdminService = Depends(get_product_admin_service),
):
    try:
        product = await service.get_product(product_id)
    except AdminProductNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return BaseResponse(data=product)


def _ids(ids: list[uuid.UUID]) -> str:
    return ", ".join(str(i) for i in ids)


# Rota estática antes das dinâmicas por clareza (métodos diferentes, sem conflito real).
@router.patch("/presentation", response_model=BaseResponse[BatchPresentationResult])
async def update_presentation_batch(
    payload: BatchPresentationRequest,
    user: User = Depends(require_role(["admin"])),
    service: PresentationService = Depends(get_presentation_service),
):
    try:
        result = await service.update_batch(payload, user.id)
    except PresentationProductNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Produtos não encontrados: {_ids(exc.missing)}"
        )
    return BaseResponse(data=result)


@router.patch("/{product_id}/presentation", response_model=BaseResponse[AdminPresentation])
async def update_presentation(
    product_id: uuid.UUID,
    payload: PresentationUpdate,
    user: User = Depends(require_role(["admin"])),
    service: PresentationService = Depends(get_presentation_service),
    products: ProductAdminService = Depends(get_product_admin_service),
):
    try:
        await service.update(product_id, payload, user.id)
    except PresentationProductNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    except PresentationCategoryNotFoundError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Categorias inexistentes ou excluídas: {_ids(exc.missing)}",
        )
    return BaseResponse(data=(await products.get_product(product_id)).presentation)
