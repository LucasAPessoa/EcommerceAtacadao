import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import Category, Product
from src.models.catalog_presentation import ProductSitePresentation, product_site_categories


class PresentationRepository:
    """Escrita da camada de apresentação. Nunca toca ``products`` nem os vínculos do Bling.

    Não faz commit: o service fecha a transação única.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def existing_product_ids(self, product_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        rows = await self.session.execute(
            select(Product.id).where(Product.id.in_(product_ids), Product.deleted_at.is_(None))
        )
        return set(rows.scalars().all())

    async def missing_category_ids(self, category_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        """IDs que não existem ou estão excluídos (categoria inativa é aceita)."""
        rows = await self.session.execute(
            select(Category.id).where(Category.id.in_(category_ids), Category.deleted_at.is_(None))
        )
        found = set(rows.scalars().all())
        return [cid for cid in category_ids if cid not in found]

    async def _ensure_rows(self, product_ids: Sequence[uuid.UUID]) -> None:
        await self.session.execute(
            pg_insert(ProductSitePresentation)
            .values([{"product_id": pid} for pid in product_ids])
            .on_conflict_do_nothing(index_elements=["product_id"])
        )

    async def upsert(
        self,
        product_id: uuid.UUID,
        values: dict[str, Any],
        user_id: uuid.UUID,
        site_category_ids: Optional[list[uuid.UUID]] = None,
    ) -> None:
        """Grava só as colunas informadas; ``site_category_ids`` substitui o vínculo do site.

        A linha é criada se faltar e nunca é apagada. ``None`` em ``site_category_ids`` deixa
        o vínculo como está; lista vazia o apaga.
        """
        await self._ensure_rows([product_id])
        row = (
            await self.session.execute(
                select(ProductSitePresentation)
                .where(ProductSitePresentation.product_id == product_id)
                .with_for_update()
            )
        ).scalar_one()
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_by_user_id = user_id
        row.updated_at = datetime.utcnow()
        if site_category_ids is not None:
            await self.session.execute(
                delete(product_site_categories).where(
                    product_site_categories.c.product_id == product_id
                )
            )
            if site_category_ids:
                await self.session.execute(
                    product_site_categories.insert(),
                    [{"product_id": product_id, "category_id": cid} for cid in site_category_ids],
                )

    async def bulk_set_flags(
        self, product_ids: Sequence[uuid.UUID], values: dict[str, bool], user_id: uuid.UUID
    ) -> None:
        ordered = sorted(product_ids)
        await self._ensure_rows(ordered)
        await self.session.execute(
            update(ProductSitePresentation)
            .where(ProductSitePresentation.product_id.in_(ordered))
            .values(**values, updated_by_user_id=user_id, updated_at=datetime.utcnow())
        )
