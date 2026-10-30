import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.admin.presentation_repository import PresentationRepository
from src.schemas.admin.presentation import (
    BatchPresentationRequest,
    BatchPresentationResult,
    PresentationUpdate,
)


class PresentationProductNotFoundError(Exception):
    def __init__(self, missing: list[uuid.UUID]):
        super().__init__("Produto não encontrado.")
        self.missing = missing


class PresentationService:
    def __init__(self, session: AsyncSession, repository: PresentationRepository):
        self.session = session
        self.repository = repository

    async def update(
        self, product_id: uuid.UUID, payload: PresentationUpdate, user_id: uuid.UUID
    ) -> None:
        """Aplica o PATCH parcial em uma transação. Qualquer erro desfaz tudo."""
        try:
            if product_id not in await self.repository.existing_product_ids([product_id]):
                raise PresentationProductNotFoundError([product_id])

            values = {
                key: value
                for key in ("visible", "featured")
                if (value := getattr(payload, key)) is not None
            }
            if values:
                await self.repository.upsert(product_id, values, user_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def update_batch(
        self, payload: BatchPresentationRequest, user_id: uuid.UUID
    ) -> BatchPresentationResult:
        ids = list(dict.fromkeys(payload.product_ids))
        try:
            found = await self.repository.existing_product_ids(ids)
            if missing := [pid for pid in ids if pid not in found]:
                raise PresentationProductNotFoundError(missing)
            values = {
                key: value
                for key in ("visible", "featured")
                if (value := getattr(payload, key)) is not None
            }
            await self.repository.bulk_set_flags(ids, values, user_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return BatchPresentationResult(updated=len(ids))
