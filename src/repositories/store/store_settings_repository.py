from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.store import STORE_SETTINGS_ID, StoreSettings


class StoreSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> Optional[StoreSettings]:
        result = await self.session.execute(
            select(StoreSettings).where(StoreSettings.id == STORE_SETTINGS_ID)
        )
        return result.scalar_one_or_none()

    async def upsert(self, theme: str, brand_color: Optional[str]) -> StoreSettings:
        """Grava a linha singleton; o upsert atômico evita corrida entre dois PUTs."""
        now = datetime.utcnow()
        stmt = insert(StoreSettings).values(
            id=STORE_SETTINGS_ID,
            theme=theme,
            brand_color=brand_color,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[StoreSettings.id],
            set_={"theme": theme, "brand_color": brand_color, "updated_at": now},
        )
        await self.session.execute(stmt)
        await self.session.commit()
        row = await self.get()
        assert row is not None
        await self.session.refresh(row)
        return row

    async def set_pricing_auto_confirm(self, auto_confirm: bool, default_theme: str) -> bool:
        """Grava só `pricing_auto_confirm`; cria a linha singleton (tema padrão) se não existir."""
        now = datetime.utcnow()
        stmt = insert(StoreSettings).values(
            id=STORE_SETTINGS_ID,
            theme=default_theme,
            pricing_auto_confirm=auto_confirm,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[StoreSettings.id],
            set_={"pricing_auto_confirm": auto_confirm, "updated_at": now},
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return auto_confirm
