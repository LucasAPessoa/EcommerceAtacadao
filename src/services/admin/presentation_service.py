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


class PresentationCategoryNotFoundError(Exception):
    def __init__(self, missing: list[uuid.UUID]):
        super().__init__("Categoria não encontrada.")
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

            values: dict[str, object] = {}
            for field in ("name", "description", "complementary_description"):
                override = getattr(payload, field)
                if override is not None:
                    values[field] = override.value if override.locked else None
            for flag in ("visible", "featured"):
                if (flag_value := getattr(payload, flag)) is not None:
                    values[flag] = flag_value

            site_ids = None
            if payload.categories is not None:
                site_ids = payload.categories.category_ids
                values["categories_locked"] = payload.categories.locked
                if missing := await self.repository.missing_category_ids(site_ids):
                    raise PresentationCategoryNotFoundError(missing)

            if values:
                await self.repository.upsert(product_id, values, user_id, site_ids)
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
