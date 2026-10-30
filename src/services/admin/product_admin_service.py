import uuid
from decimal import Decimal
from typing import Any

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
from src.models.catalog import ProductVariant
from src.models.enums import PriceSource
from src.repositories.admin.admin_product_repository import (
    AdminProductRepository,
    ProductListFilters,
)
from src.schemas.admin.products import (
    AdminPresentation,
    AdminPricingTier,
    AdminProductDetail,
    AdminProductListItem,
    AdminVariant,
    BlingCategory,
    PendingReason,
    PricingStatusValue,
    PricingWarning,
    UpdatedBy,
)
from src.services.sales.pricing import is_variant_published

_REASONS = {
    INCOMPLETE_WEIGHT: PendingReason.INCOMPLETE_WEIGHT,
    INCOMPLETE_DIMENSIONS: PendingReason.INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE: PendingReason.INCOMPLETE_PRICE,
    PendingReason.PRICE_NOT_SET.value: PendingReason.PRICE_NOT_SET,
    PendingReason.STORE_PRICE_MISSING.value: PendingReason.STORE_PRICE_MISSING,
    PendingReason.TIER_NOT_BELOW_UNIT.value: PendingReason.TIER_NOT_BELOW_UNIT,
}


class AdminProductNotFoundError(Exception):
    pass


def variant_warnings(variant: ProductVariant) -> list[PricingWarning]:
    """Avisos de preço da variação (mesmas regras de ``_expressions``, em memória).

    Exige ``variant.product`` e ``variant.pricing_tiers`` carregados.
    """
    warnings: list[PricingWarning] = []
    line_one = next((t for t in variant.pricing_tiers if t.min_quantity == 1), None)
    general = variant.price_source == PriceSource.GENERAL
    if line_one is not None and any(
        t.min_quantity > 1 and Decimal(t.unit_price) >= Decimal(line_one.unit_price)
        for t in variant.pricing_tiers
    ):
        warnings.append(PricingWarning.TIER_NOT_BELOW_UNIT)
    if general and is_variant_published(variant):
        warnings.append(PricingWarning.STORE_PRICE_MISSING)
    if general and variant.product.store_listed and Decimal(variant.base_price) <= 0:
        warnings.append(PricingWarning.PRICE_NOT_SET)
    return warnings


def variant_pricing_fields(variant: ProductVariant) -> dict[str, Any]:
    """Campos de preço da variação no formato do contrato (detalhe e PUT da tabela)."""
    tiers = sorted(variant.pricing_tiers, key=lambda t: t.min_quantity)
    return {
        "published": is_variant_published(variant),
        "price_source": variant.price_source.value.lower() if variant.price_source else None,
        "store_price": variant.store_price,
        "pricing_status": variant.pricing_status.value.lower(),
        "pricing_confirmed_at": variant.pricing_confirmed_at,
        "pricing_tiers": [
            AdminPricingTier(id=t.id, min_quantity=t.min_quantity, unit_price=t.unit_price)
            for t in tiers
        ],
        "warnings": variant_warnings(variant),
    }


class ProductAdminService:
    def __init__(self, repository: AdminProductRepository):
        self.repository = repository

    async def list_products(
        self, filters: ProductListFilters, skip: int, limit: int
    ) -> tuple[list[AdminProductListItem], int]:
        rows, total = await self.repository.list(filters, skip, limit)
        items = []
        for row in rows:
            warnings = [
                warning
                for warning, column in (
                    (PricingWarning.TIER_NOT_BELOW_UNIT, "tier_warning"),
                    (PricingWarning.STORE_PRICE_MISSING, "store_price_missing"),
                    (PricingWarning.PRICE_NOT_SET, "price_not_set"),
                )
                if row[column] > 0
            ]
            pricing_status = (
                PricingStatusValue.PENDING
                if row["pricing_pending"] > 0
                else PricingStatusValue.CONFIRMED
            )
            items.append(
                AdminProductListItem.model_validate(
                    {**row, "warnings": warnings, "pricing_status": pricing_status}
                )
            )
        return items, total

    async def get_product(self, product_id: uuid.UUID) -> AdminProductDetail:
        data = await self.repository.get_detail(product_id)
        if data is None:
            raise AdminProductNotFoundError()
        p, pres = data.product, data.presentation

        updated_by = data.updated_by
        presentation = AdminPresentation(
            visible=pres.visible if pres else True,
            featured=pres.featured if pres else False,
            updated_at=pres.updated_at if pres else None,
            updated_by=(
                UpdatedBy(id=updated_by.id, full_name=updated_by.full_name) if updated_by else None
            ),
        )
        variants = [
            AdminVariant(
                id=v.id,
                bling_sku=v.bling_sku,
                gtin=v.gtin,
                variation_name=v.variation_name,
                base_price=v.base_price,
                stock_quantity=v.stock_quantity,
                is_active=v.is_active,
                weight_kg=v.weight_kg,
                height_cm=v.height_cm,
                width_cm=v.width_cm,
                length_cm=v.length_cm,
                pending_reason=_REASONS[reason] if reason else None,
                images=[
                    i.image_url
                    for i in sorted(v.images, key=lambda i: (not i.is_main, i.created_at, i.id))
                ],
                **variant_pricing_fields(v),
            )
            for v, reason in data.variants
        ]
        # Imagens do produto: as das variações, principal primeiro, sem repetir.
        images = list(dict.fromkeys(url for v in variants for url in v.images))
        return AdminProductDetail(
            id=p.id,
            bling_id=p.bling_id,
            code=p.code,
            name=p.name,
            description=p.description,
            complementary_description=p.complementary_description,
            images=images,
            categories=[BlingCategory(id=c.id, name=c.name) for c in data.bling_categories],
            brand=p.brand,
            unit=p.unit,
            status=p.status,
            is_active=p.is_active,
            bling_updated_at=p.bling_updated_at,
            variants=variants,
            presentation=presentation,
        )


__all__ = [
    "AdminProductNotFoundError",
    "ProductAdminService",
    "variant_pricing_fields",
    "variant_warnings",
]
