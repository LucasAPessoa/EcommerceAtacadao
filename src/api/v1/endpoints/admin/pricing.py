"""Rotas admin de preço por variação (spec 008, T013)."""

import uuid
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.endpoints.admin.products import get_product_admin_service
from src.core.db import AsyncSessionLocal, DbSession
from src.models.catalog import ProductVariant
from src.repositories.catalog.store_pricing_repository import StorePricingRepository
from src.schemas.admin.pricing import (
    AdminVariantPricing,
    ConfirmPricingBatch,
    ConfirmPricingResult,
    VariantPricingUpdate,
)
from src.schemas.admin.products import AdminPricingTier, AdminProductDetail
from src.schemas.response_schema import BaseResponse
from src.services.admin.product_admin_service import (
    AdminProductNotFoundError,
    ProductAdminService,
)
from src.services.catalog.catalog_sync_service import build_catalog_client
from src.services.catalog.store_pricing_service import (
    PriceTierInput,
    StorePricingBlingError,
    StorePricingConflictError,
    StorePricingError,
    StorePricingNotFoundError,
    StorePricingService,
    StorePricingValidationError,
)

router = APIRouter(prefix="/products", tags=["Admin - Pricing"])

_STATUS_BY_ERROR: list[tuple[type[StorePricingError], int]] = [
    (StorePricingNotFoundError, status.HTTP_404_NOT_FOUND),
    (StorePricingValidationError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (StorePricingConflictError, status.HTTP_409_CONFLICT),
    (StorePricingBlingError, status.HTTP_502_BAD_GATEWAY),
]


def get_store_pricing_service(session: DbSession) -> StorePricingService:
    # O cliente do Bling usa sessões curtas próprias para o token (sem tocar nesta sessão).
    return StorePricingService(
        session, StorePricingRepository(session), build_catalog_client(AsyncSessionLocal)
    )


def _raise(exc: StorePricingError) -> NoReturn:
    for error_type, code in _STATUS_BY_ERROR:
        if isinstance(exc, error_type):
            raise HTTPException(code, detail=exc.message)
    raise exc


def _variant_response(variant: ProductVariant) -> AdminVariantPricing:
    tiers = sorted(variant.pricing_tiers, key=lambda t: t.min_quantity)
    return AdminVariantPricing(
        id=variant.id,
        variation_name=variant.variation_name,
        is_active=variant.is_active,
        published=any(t.min_quantity == 1 for t in tiers),
        price_source=variant.price_source.value.lower() if variant.price_source else None,
        store_price=variant.store_price,
        pricing_status=variant.pricing_status.value.lower(),
        pricing_confirmed_at=variant.pricing_confirmed_at,
        pricing_tiers=[
            AdminPricingTier(id=t.id, min_quantity=t.min_quantity, unit_price=t.unit_price)
            for t in tiers
        ],
    )


# Rota estática do lote antes das dinâmicas por clareza.
@router.post("/confirm-pricing", response_model=BaseResponse[ConfirmPricingResult])
async def confirm_pricing_batch(
    payload: ConfirmPricingBatch,
    service: StorePricingService = Depends(get_store_pricing_service),
):
    result = await service.confirm_many(payload.product_ids)
    return BaseResponse(
        data=ConfirmPricingResult(confirmed=result.confirmed, skipped=result.skipped)
    )


@router.post("/{product_id}/confirm-pricing", response_model=BaseResponse[AdminProductDetail])
async def confirm_pricing(
    product_id: uuid.UUID,
    service: StorePricingService = Depends(get_store_pricing_service),
    products: ProductAdminService = Depends(get_product_admin_service),
):
    try:
        await service.confirm(product_id)
        detail = await products.get_product(product_id)
    except StorePricingError as exc:
        _raise(exc)
    except AdminProductNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return BaseResponse(data=detail)


@router.put(
    "/{product_id}/variants/{variant_id}/pricing",
    response_model=BaseResponse[AdminVariantPricing],
)
async def save_variant_pricing(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantPricingUpdate,
    service: StorePricingService = Depends(get_store_pricing_service),
):
    tiers = [PriceTierInput(t.min_quantity, t.unit_price) for t in payload.tiers]
    try:
        variant = await service.save_table(product_id, variant_id, payload.unit_price, tiers)
    except StorePricingError as exc:
        _raise(exc)
    return BaseResponse(data=_variant_response(variant))
