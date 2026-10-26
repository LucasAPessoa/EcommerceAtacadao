import uuid
from typing import Optional

from sqlalchemy import Boolean, Column, ForeignKey, Index, String, Table, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

product_site_categories = Table(
    "product_site_categories",
    Base.metadata,
    Column(
        "product_id",
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        PGUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ProductSitePresentation(Base, TimestampMixin):
    """Camada de apresentação do site por produto (esparsa). NULL = usar o valor do Bling."""

    __tablename__ = "product_site_presentation"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    complementary_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    categories_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_product_site_presentation_hidden",
            "visible",
            postgresql_where=text("visible = false"),
        ),
        Index(
            "ix_product_site_presentation_featured",
            "featured",
            postgresql_where=text("featured = true"),
        ),
    )
