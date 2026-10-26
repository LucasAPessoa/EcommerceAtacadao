import uuid
from typing import Optional

from src.integrations.bling.catalog import (
    INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE,
    INCOMPLETE_WEIGHT,
)
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
    CategoriesField,
    PendingReason,
    SiteCategory,
    TextField,
    UpdatedBy,
)

_REASONS = {
    INCOMPLETE_WEIGHT: PendingReason.INCOMPLETE_WEIGHT,
    INCOMPLETE_DIMENSIONS: PendingReason.INCOMPLETE_DIMENSIONS,
    INCOMPLETE_PRICE: PendingReason.INCOMPLETE_PRICE,
}


class AdminProductNotFoundError(Exception):
    pass


class ProductAdminService:
    def __init__(self, repository: AdminProductRepository):
        self.repository = repository

    async def list_products(
        self, filters: ProductListFilters, skip: int, limit: int
    ) -> tuple[list[AdminProductListItem], int]:
        rows, total = await self.repository.list(filters, skip, limit)
        return [AdminProductListItem.model_validate(row) for row in rows], total

    async def get_product(self, product_id: uuid.UUID) -> AdminProductDetail:
        data = await self.repository.get_detail(product_id)
        if data is None:
            raise AdminProductNotFoundError()
        p, pres = data.product, data.presentation

        def text(bling: Optional[str], site: Optional[str]) -> TextField:
            return TextField(bling=bling, site=site, locked=site is not None)

        updated_by = data.updated_by
        presentation = AdminPresentation(
            name=text(p.name, pres.name if pres else None),
            description=text(p.description, pres.description if pres else None),
            complementary_description=text(
                p.complementary_description, pres.complementary_description if pres else None
            ),
            categories=CategoriesField(
                bling=[BlingCategory(id=c.id, name=c.name) for c in data.bling_categories],
                site=[
                    SiteCategory(id=c.id, name=c.name, is_active=c.is_active)
                    for c in data.site_categories
                ],
                locked=bool(pres and pres.categories_locked),
            ),
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
            )
            for v, reason in data.variants
        ]
        return AdminProductDetail(
            id=p.id,
            bling_id=p.bling_id,
            code=p.code,
            brand=p.brand,
            unit=p.unit,
            status=p.status,
            is_active=p.is_active,
            bling_updated_at=p.bling_updated_at,
            variants=variants,
            pricing_tiers=[
                AdminPricingTier(id=t.id, min_quantity=t.min_quantity, unit_price=t.unit_price)
                for t in data.pricing_tiers
            ],
            presentation=presentation,
        )
