"""pricing_tiers_variant

Faixas de preço passam a pertencer a uma variação (embalagem).

Revision ID: b4f8c2d71e35
Revises: a7c3e91b4d20
Create Date: 2026-10-28 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4f8c2d71e35"
down_revision: Union[str, Sequence[str], None] = "a7c3e91b4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Variação alvo: ativa (e não deletada) de menor base_price com base_price > unit_price;
# senão ativa de menor base_price; senão qualquer de menor base_price. Empate: menor id.
_BACKFILL = """
UPDATE pricing_tiers AS t
SET variant_id = (
    SELECT v.id
    FROM product_variants AS v
    WHERE v.product_id = t.product_id
    ORDER BY
        (v.is_active AND v.deleted_at IS NULL AND v.base_price > t.unit_price) DESC,
        (v.is_active AND v.deleted_at IS NULL) DESC,
        v.base_price ASC,
        v.id ASC
    LIMIT 1
)
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "pricing_tiers",
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(_BACKFILL)

    orphans = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM pricing_tiers WHERE variant_id IS NULL"))
        .scalar_one()
    )
    if orphans:
        raise RuntimeError(
            f"{orphans} faixa(s) de preço pertencem a produtos sem nenhuma variação; "
            "corrija ou remova-as manualmente antes de migrar (nada foi apagado)."
        )

    op.alter_column("pricing_tiers", "variant_id", nullable=False)
    op.create_foreign_key(
        "fk_pricing_tiers_variant_id_product_variants",
        "pricing_tiers",
        "product_variants",
        ["variant_id"],
        ["id"],
    )
    op.create_index(op.f("ix_pricing_tiers_variant_id"), "pricing_tiers", ["variant_id"])
    op.create_unique_constraint(
        "uq_pricing_tiers_variant_min", "pricing_tiers", ["variant_id", "min_quantity"]
    )
    op.drop_constraint("uq_pricing_tiers_product_min", "pricing_tiers", type_="unique")


def downgrade() -> None:
    """Downgrade schema.

    Falha se duas faixas do mesmo produto tiverem a mesma min_quantity (variações distintas).
    """
    op.create_unique_constraint(
        "uq_pricing_tiers_product_min", "pricing_tiers", ["product_id", "min_quantity"]
    )
    op.drop_constraint("uq_pricing_tiers_variant_min", "pricing_tiers", type_="unique")
    op.drop_index(op.f("ix_pricing_tiers_variant_id"), table_name="pricing_tiers")
    op.drop_constraint(
        "fk_pricing_tiers_variant_id_product_variants", "pricing_tiers", type_="foreignkey"
    )
    op.drop_column("pricing_tiers", "variant_id")
