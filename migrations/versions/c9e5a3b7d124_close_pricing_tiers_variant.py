"""fecha faixas de preço: variant_id obrigatório, remove product_id

Revision ID: c9e5a3b7d124
Revises: b8d4f2a6c913
Create Date: 2026-10-29 09:00:00.000000

Fechamento do PR 2b (spec 008): apaga as faixas legadas sem variação (sem uso desde o
PR 2; a contagem apagada é impressa no upgrade), torna `variant_id` NOT NULL e remove
o índice único legado e a coluna `product_id` (com a FK). O downgrade recria a coluna
nula, o índice e a FK, sem restaurar dados.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e5a3b7d124"
down_revision: Union[str, Sequence[str], None] = "b8d4f2a6c913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    deleted = bind.execute(sa.text("DELETE FROM pricing_tiers WHERE variant_id IS NULL")).rowcount
    print(f"pricing_tiers legadas sem variant_id apagadas: {deleted}")
    op.drop_index("uq_pricing_tiers_product_min_legacy", table_name="pricing_tiers")
    op.alter_column("pricing_tiers", "variant_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("pricing_tiers_product_id_fkey", "pricing_tiers", type_="foreignkey")
    op.drop_column("pricing_tiers", "product_id")


def downgrade() -> None:
    """Downgrade schema (não restaura dados)."""
    op.add_column("pricing_tiers", sa.Column("product_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "pricing_tiers_product_id_fkey", "pricing_tiers", "products", ["product_id"], ["id"]
    )
    op.alter_column("pricing_tiers", "variant_id", existing_type=sa.UUID(), nullable=True)
    op.create_index(
        "uq_pricing_tiers_product_min_legacy",
        "pricing_tiers",
        ["product_id", "min_quantity"],
        unique=True,
        postgresql_where=sa.text("variant_id IS NULL"),
    )
