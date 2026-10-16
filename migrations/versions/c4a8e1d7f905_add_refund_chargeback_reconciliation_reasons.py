"""add refund and chargeback reconciliation reasons

Revision ID: c4a8e1d7f905
Revises: b7e41c05d2a9
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c4a8e1d7f905"
down_revision: Union[str, Sequence[str], None] = "b7e41c05d2a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_REASONS = ("PAYMENT_REFUNDED", "PAYMENT_PARTIALLY_REFUNDED", "PAYMENT_CHARGEBACK")


def upgrade() -> None:
    # ADD VALUE não pode ser usado na mesma transação em que é criado; o bloco
    # autocommit isola o DDL e nenhum dado novo é escrito nesta migração.
    with op.get_context().autocommit_block():
        for value in NEW_REASONS:
            op.execute(f"ALTER TYPE reconciliationreasonenum ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL não remove valores de enum; os valores extras são inofensivos.
    pass
