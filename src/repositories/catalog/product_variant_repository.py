from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import Product, ProductVariant
from src.repositories.base_repository import BaseRepository
from src.repositories.catalog._published import purchasable
from src.schemas.catalog.product_variant_schema import ProductVariantPublicSchema


class ProductVariantRepository(BaseRepository[ProductVariant, ProductVariantPublicSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=ProductVariant, response_schema=ProductVariantPublicSchema, session=session
        )

    async def get_active_for_shipping(self, variant_id: UUID) -> Optional[ProductVariant]:
        """Busca somente o SKU comercialmente disponível para uma cotação pública."""
        query = (
            select(ProductVariant)
            .join(ProductVariant.product)
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.is_active.is_(True),
                ProductVariant.deleted_at.is_(None),
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_for_sale(self, variant_id: UUID) -> Optional[ProductVariant]:
        """Modelo da variação (não apagada) com produto e tabela, para validar a compra."""
        result = await self.session.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product),
                selectinload(ProductVariant.pricing_tiers),
            )
            .where(ProductVariant.id == variant_id, ProductVariant.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _public_query():
        """Variações que a loja pública mostra: publicadas e com preço confirmado."""
        return (
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .options(selectinload(ProductVariant.pricing_tiers))
            .where(Product.deleted_at.is_(None), purchasable(ProductVariant, Product))
        )

    async def get_by_id(self, id: UUID) -> Optional[ProductVariantPublicSchema]:
        result = await self.session.execute(self._public_query().where(ProductVariant.id == id))
        variant = result.scalar_one_or_none()
        return self.response_schema.model_validate(variant) if variant else None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ProductVariantPublicSchema]:
        result = await self.session.execute(
            self._public_query()
            .order_by(ProductVariant.created_at, ProductVariant.id)
            .offset(skip)
            .limit(limit)
        )
        return [self.response_schema.model_validate(v) for v in result.scalars().all()]

    async def get_by_product(self, product_id: UUID) -> List[ProductVariantPublicSchema]:
        result = await self.session.execute(
            self._public_query()
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.created_at, ProductVariant.id)
        )
        return [self.response_schema.model_validate(v) for v in result.scalars().all()]
