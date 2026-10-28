from typing import Optional

from sqlalchemy import CheckConstraint, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

STORE_SETTINGS_ID = 1


class StoreSettings(Base, TimestampMixin):
    """Configuração da loja do deploy (singleton: uma única linha, id = 1)."""

    __tablename__ = "store_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_store_settings_singleton"),)

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, default=STORE_SETTINGS_ID, server_default=text("1")
    )
    theme: Mapped[str] = mapped_column(String(50), nullable=False)
    brand_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
