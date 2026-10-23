from uuid import UUID

from fastapi import Depends, HTTPException, status

from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.core.db import DbSession
from src.core.sec import require_role
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.catalog.product_variant_schema import (
    ProductVariantPriceUpdateSchema,
    ProductVariantResponseSchema,
    ProductVariantUpdateSchema,
)
from src.schemas.response_schema import BaseResponse
from src.services.catalog.product_variant_service import ProductVariantService


def get_product_variant_service(
    session: DbSession,
) -> ProductVariantService:
    repository = ProductVariantRepository(session)
    return ProductVariantService(repository)


router = build_crud_router(
    prefix="/product-variants",
    tags=["Product Variants"],
    service_dependency=get_product_variant_service,
    response_schema=ProductVariantResponseSchema,
    verbs={
        "list": "list_variants",
        "get": "get_variant_by_id",
    },
    not_found_message="Variação do produto não encontrada.",
    read_only=True,
    list_filters={"product_id": "Filtra pelo produto (UUID)."},
)


@router.patch("/{item_id}", response_model=BaseResponse[ProductVariantResponseSchema])
async def update_variant_price(
    item_id: UUID,
    payload: ProductVariantPriceUpdateSchema,
    service: ProductVariantService = Depends(get_product_variant_service),
    _admin=Depends(require_role(["admin"])),
):
    """Único campo editável do catálogo pela API: preço base da variação."""
    data = await service.update_variant(
        item_id, ProductVariantUpdateSchema(base_price=payload.base_price)
    )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variação do produto não encontrada.",
        )
    return BaseResponse(status="success", data=data)
