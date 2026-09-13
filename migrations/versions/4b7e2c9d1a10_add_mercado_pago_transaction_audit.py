"""add mercado pago transaction audit

Revision ID: 4b7e2c9d1a10
Revises: 31a9c6e2f4b8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4b7e2c9d1a10"
down_revision: Union[str, Sequence[str], None] = "31a9c6e2f4b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("gateway_provider", sa.String(length=40), nullable=False, server_default="LOCAL"),
    )
    op.add_column("transactions", sa.Column("gateway_payment_id", sa.String(length=100)))
    op.add_column("transactions", sa.Column("checkout_url", sa.Text()))
    op.add_column("transactions", sa.Column("gateway_status_detail", sa.String(length=100)))
    op.add_column("transactions", sa.Column("webhook_processed_at", sa.DateTime()))
    op.create_unique_constraint(
        "uq_transactions_gateway_payment_id", "transactions", ["gateway_payment_id"]
    )
    op.alter_column("transactions", "gateway_provider", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_transactions_gateway_payment_id", "transactions", type_="unique")
    op.drop_column("transactions", "webhook_processed_at")
    op.drop_column("transactions", "gateway_status_detail")
    op.drop_column("transactions", "checkout_url")
    op.drop_column("transactions", "gateway_payment_id")
    op.drop_column("transactions", "gateway_provider")
