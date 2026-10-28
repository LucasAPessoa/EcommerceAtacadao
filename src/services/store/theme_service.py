from typing import Optional

from src.repositories.store.store_settings_repository import StoreSettingsRepository
from src.schemas.store.theme import StoreThemeResponse, ThemeInfoSchema
from src.services.store.themes import DEFAULT_THEME, THEMES


class StoreThemeService:
    def __init__(self, repository: StoreSettingsRepository):
        self.repository = repository

    async def get_theme(self) -> StoreThemeResponse:
        row = await self.repository.get()
        if row is None:
            return StoreThemeResponse(theme=DEFAULT_THEME, brand_color=None, updated_at=None)
        return StoreThemeResponse(
            theme=row.theme, brand_color=row.brand_color, updated_at=row.updated_at
        )

    async def set_theme(self, theme: str, brand_color: Optional[str]) -> StoreThemeResponse:
        row = await self.repository.upsert(theme, brand_color)
        return StoreThemeResponse(
            theme=row.theme, brand_color=row.brand_color, updated_at=row.updated_at
        )

    @staticmethod
    def list_themes() -> list[ThemeInfoSchema]:
        return [
            ThemeInfoSchema(key=t.key, name=t.name, description=t.description)
            for t in THEMES.values()
        ]
