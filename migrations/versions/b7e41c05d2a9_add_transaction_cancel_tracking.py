"""add remote cancel tracking to transactions

Revision ID: b7e41c05d2a9
Revises: 9d3e5b7c1a42
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e41c05d2a9"
down_revision: Union[str, Sequence[str], None] = "9d3e5b7c1a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aditiva e nullable: transações existentes permanecem válidas sem backfill.
    op.add_column("transactions", sa.Column("cancel_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("transactions", sa.Column("cancel_attempts", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("cancel_last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column(
        "transactions", sa.Column("cancel_last_error_code", sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("transactions", "cancel_last_error_code")
    op.drop_column("transactions", "cancel_last_attempt_at")
    op.drop_column("transactions", "cancel_attempts")
    op.drop_column("transactions", "cancel_confirmed_at")
