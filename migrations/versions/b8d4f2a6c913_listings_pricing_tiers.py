"""anúncios do Bling: faixas de preço por embalagem

Revision ID: b8d4f2a6c913
Revises: a7c3e91b4d20
Create Date: 2026-10-28 09:00:00.000000

As faixas existentes são APAGADAS no upgrade (decisão do usuário, spec 008 FR-014).
O downgrade reverte apenas o schema e NÃO restaura as faixas apagadas; se houver
faixas com `variant_id` ou `min_quantity = 1`, ele as remove para poder recriar a
unicidade por produto e o check `min_quantity > 1`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8d4f2a6c913"
down_revision: Union[str, Sequence[str], None] = "a7c3e91b4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

price_source = postgresql.ENUM("VARIANT_LINK", "PARENT_LINK", "GENERAL", name="pricesource")
pricing_status = postgresql.ENUM("PENDING", "CONFIRMED", name="pricingstatus")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DELETE FROM pricing_tiers")

    price_source.create(op.get_bind(), checkfirst=True)
    pricing_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "store_settings",
        sa.Column(
            "pricing_auto_confirm", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column("products", sa.Column("bling_store_link_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "products",
        sa.Column("store_listed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "product_variants", sa.Column("bling_store_link_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("product_variants", sa.Column("store_price", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "product_variants",
        sa.Column(
            "price_source", postgresql.ENUM(name="pricesource", create_type=False), nullable=True
        ),
    )
    op.add_column(
        "product_variants",
        sa.Column(
            "pricing_status",
            postgresql.ENUM(name="pricingstatus", create_type=False),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "product_variants", sa.Column("pricing_confirmed_at", sa.DateTime(), nullable=True)
    )

    op.add_column("pricing_tiers", sa.Column("variant_id", sa.UUID(), nullable=True))
    op.alter_column("pricing_tiers", "product_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        "fk_pricing_tiers_variant_id_product_variants",
        "pricing_tiers",
        "product_variants",
        ["variant_id"],
        ["id"],
    )
    op.create_index("ix_pricing_tiers_variant_id", "pricing_tiers", ["variant_id"])
    op.drop_constraint("uq_pricing_tiers_product_min", "pricing_tiers", type_="unique")
    op.drop_constraint("ck_pricing_tiers_min_quantity", "pricing_tiers", type_="check")
    op.create_check_constraint(
        "ck_pricing_tiers_min_quantity", "pricing_tiers", "min_quantity >= 1"
    )
    op.create_unique_constraint(
        "uq_pricing_tiers_variant_min", "pricing_tiers", ["variant_id", "min_quantity"]
    )
    op.create_index(
        "uq_pricing_tiers_product_min_legacy",
        "pricing_tiers",
        ["product_id", "min_quantity"],
        unique=True,
        postgresql_where=sa.text("variant_id IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema (não restaura as faixas apagadas no upgrade)."""
    op.execute(
        "DELETE FROM pricing_tiers "
        "WHERE variant_id IS NOT NULL OR product_id IS NULL OR min_quantity < 2"
    )
    op.drop_index("uq_pricing_tiers_product_min_legacy", table_name="pricing_tiers")
    op.drop_constraint("uq_pricing_tiers_variant_min", "pricing_tiers", type_="unique")
    op.drop_constraint("ck_pricing_tiers_min_quantity", "pricing_tiers", type_="check")
    op.create_check_constraint("ck_pricing_tiers_min_quantity", "pricing_tiers", "min_quantity > 1")
    op.create_unique_constraint(
        "uq_pricing_tiers_product_min", "pricing_tiers", ["product_id", "min_quantity"]
    )
    op.drop_index("ix_pricing_tiers_variant_id", table_name="pricing_tiers")
    op.drop_constraint(
        "fk_pricing_tiers_variant_id_product_variants", "pricing_tiers", type_="foreignkey"
    )
    op.alter_column("pricing_tiers", "product_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("pricing_tiers", "variant_id")

    op.drop_column("product_variants", "pricing_confirmed_at")
    op.drop_column("product_variants", "pricing_status")
    op.drop_column("product_variants", "price_source")
    op.drop_column("product_variants", "store_price")
    op.drop_column("product_variants", "bling_store_link_id")
    op.drop_column("products", "store_listed")
    op.drop_column("products", "bling_store_link_id")
    op.drop_column("store_settings", "pricing_auto_confirm")

    pricing_status.drop(op.get_bind(), checkfirst=True)
    price_source.drop(op.get_bind(), checkfirst=True)
