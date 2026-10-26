import uuid
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.endpoints.admin._params import PageParams, page_params
from src.core.client_config import get_client_config
from src.core.db import DbSession
from src.repositories.admin.admin_product_repository import (
    AdminProductRepository,
    ProductListFilters,
)
from src.schemas.admin.products import AdminProductDetail, AdminProductListItem
from src.schemas.response_schema import BaseResponse, PageMeta
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
