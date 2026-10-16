"""enforce one transaction per order

Revision ID: 9d3e5b7c1a42
Revises: 6c2d9f8a7b11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9d3e5b7c1a42"
down_revision: Union[str, Sequence[str], None] = "6c2d9f8a7b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Bloqueia escritas até o fim da migração: nenhuma duplicata pode surgir entre a
    # checagem e o CREATE INDEX (que tomaria o mesmo lock SHARE de qualquer forma).
    op.execute("LOCK TABLE transactions IN SHARE MODE")
    # Em modo offline (--sql) não há conexão para consultar; a checagem só roda online.
    if not op.get_context().as_sql:
        duplicates = bind.execute(
            sa.text(
                "SELECT count(*) FROM ("
                "SELECT order_id FROM transactions GROUP BY order_id HAVING count(*) > 1"
                ") AS d"
            )
        ).scalar_one()
        if duplicates:
            raise RuntimeError(
                f"Abortando: {duplicates} pedido(s) possuem mais de uma transação em "
                "transactions.order_id. Resolva manualmente antes de criar o índice único "
                "uq_transactions_order_id; nenhum dado foi alterado."
            )
    op.create_index("uq_transactions_order_id", "transactions", ["order_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_transactions_order_id", table_name="transactions")
