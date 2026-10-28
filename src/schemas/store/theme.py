import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from src.services.store.themes import THEMES

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ThemeInfoSchema(BaseModel):
    key: str
    name: str
    description: str


class StoreThemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    brand_color: Optional[str] = None

    @field_validator("theme")
    @classmethod
    def _theme_in_catalog(cls, value: str) -> str:
        if value not in THEMES:
            raise ValueError(f"Tema inválido. Disponíveis: {', '.join(THEMES)}.")
        return value

    @field_validator("brand_color")
    @classmethod
    def _color_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _HEX_COLOR.match(value):
            raise ValueError("Cor inválida. Use o formato #RRGGBB.")
        return value.upper()


class StoreThemeResponse(BaseModel):
    theme: str
    brand_color: Optional[str] = None
    updated_at: Optional[datetime] = None
