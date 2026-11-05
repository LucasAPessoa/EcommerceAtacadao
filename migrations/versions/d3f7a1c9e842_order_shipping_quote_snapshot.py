"""pedido guarda a cotação de frete usada (#62)

Revision ID: d3f7a1c9e842
Revises: c9e5a3b7d124
Create Date: 2026-11-05 10:00:00.000000

Coluna aditiva e nula `orders.shipping_quote_snapshot` (JSONB): serviço, preços, prazos
e `packages` cotados no Melhor Envio. Pedidos antigos ficam com NULL. O downgrade remove
a coluna.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d3f7a1c9e842"
down_revision: Union[str, Sequence[str], None] = "c9e5a3b7d124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "orders",
        sa.Column("shipping_quote_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("orders", "shipping_quote_snapshot")
