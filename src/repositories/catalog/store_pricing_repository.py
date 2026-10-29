"""Persistência da tabela de preços por variação (spec 008)."""

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import Product, ProductVariant


class StorePricingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_variant_edits(self, variant_id: UUID) -> None:
        """Serializa edições da mesma variação até o fim da transação (advisory lock).

        Não bloqueia checkout nem pagamento, que travam a linha com FOR UPDATE: só quem edita
        a tabela de preços da mesma variação espera aqui."""
        key = int.from_bytes(variant_id.bytes[:8], "big", signed=True)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    async def get_variant(self, product_id: UUID, variant_id: UUID) -> ProductVariant | None:
        """Variação do produto lida sem lock de linha."""
        result = await self.session.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product),
                selectinload(ProductVariant.pricing_tiers),
            )
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_variant_locked(self, product_id: UUID, variant_id: UUID) -> ProductVariant | None:
        """Variação do produto, travada e relida (valida estado só depois do lock)."""
        result = await self.session.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product),
                selectinload(ProductVariant.pricing_tiers),
            )
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
            .with_for_update(of=ProductVariant)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_published_variants_locked(
        self, product_ids: Sequence[UUID]
    ) -> list[ProductVariant]:
        """Variações publicadas dos produtos, travadas em ordem estável."""
        result = await self.session.execute(
            select(ProductVariant)
            .options(selectinload(ProductVariant.pricing_tiers))
            .where(
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.is_active.is_(True),
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(ProductVariant.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def existing_product_ids(self, product_ids: Sequence[UUID]) -> set[UUID]:
        result = await self.session.execute(
            select(Product.id).where(Product.id.in_(product_ids), Product.deleted_at.is_(None))
        )
        return set(result.scalars().all())
