import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import Product
from src.models.catalog_presentation import ProductSitePresentation


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
    ) -> None:
        """Grava só as colunas informadas. A linha é criada se faltar e nunca é apagada."""
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
