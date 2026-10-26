from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.repositories.catalog.product_repository import ProductRepository
from src.schemas.catalog.product_schema import (
    ProductResponseSchema,
)
from src.schemas.response_schema import BaseResponse
from src.services.catalog.product_service import ProductService


def get_product_service(
    session: DbSession,
) -> ProductService:
    repository = ProductRepository(session)
    return ProductService(repository)


router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/code/{code}", response_model=BaseResponse[ProductResponseSchema])
async def get_product_by_code(
    code: str,
    service: ProductService = Depends(get_product_service),
):
    product = await service.get_product_by_code(code)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )
    return BaseResponse(status="success", data=product)


crud_router = build_crud_router(
    prefix="",
    tags=["Products"],
    service_dependency=get_product_service,
    response_schema=ProductResponseSchema,
    verbs={
        "list": "list_products",
        "get": "get_product_by_id",
    },
    not_found_message="Produto não encontrado, che.",
    supports_pagination=True,
    read_only=True,
)

router.include_router(crud_router)
