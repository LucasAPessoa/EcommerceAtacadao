"""bling ids bigint

Revision ID: d1e5a7b3c902
Revises: 87b8656132d8
Create Date: 2026-10-26 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e5a7b3c902"
down_revision: Union[str, Sequence[str], None] = "87b8656132d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    "categories",
    "products",
    "product_variants",
    "product_listings",
    "listing_images",
)


def upgrade() -> None:
    # Ids reais do Bling têm 11 dígitos (> int32). Índices/unique são preservados.
    for table in COLUMNS:
        op.alter_column(
            table,
            "bling_id",
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Falha se existir bling_id fora do intervalo int32.
    for table in COLUMNS:
        op.alter_column(
            table,
            "bling_id",
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )
