"""spec 009: fila de ações no Bling, colunas de pedido e leitura de saldo

Revision ID: e2a7c4d9b315
Revises: c9e5a3b7d124
Create Date: 2026-11-01 10:00:00.000000

Aditiva: colunas nulas em `orders`, `stock_reservations` e `product_variants`, e a
tabela `bling_order_actions` (UNIQUE (order_id, kind), índice parcial dos PENDING).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e2a7c4d9b315"
down_revision: Union[str, Sequence[str], None] = "c9e5a3b7d124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KIND = ("CREATE", "MARK_PAID", "POST_STOCK", "REVERSE_STOCK", "CANCEL")
STATUS = ("PENDING", "DONE", "FAILED", "SKIPPED")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("product_variants", sa.Column("stock_read_at", sa.DateTime(), nullable=True))
    op.add_column(
        "stock_reservations", sa.Column("bling_reflected_at", sa.DateTime(), nullable=True)
    )
    op.add_column("orders", sa.Column("bling_order_id", sa.BigInteger(), nullable=True))
    op.add_column("orders", sa.Column("bling_order_number", sa.String(length=30), nullable=True))
    op.add_column("orders", sa.Column("bling_order_created_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("bling_situation_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("bling_stock_posted_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("bling_stock_reversed_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("stock_cancel_reason", sa.String(length=40), nullable=True))
    op.create_unique_constraint("uq_orders_bling_order_id", "orders", ["bling_order_id"])

    postgresql.ENUM(*KIND, name="bling_order_action_kind").create(op.get_bind())
    postgresql.ENUM(*STATUS, name="bling_order_action_status").create(op.get_bind())
    op.create_table(
        "bling_order_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(*KIND, name="bling_order_action_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*STATUS, name="bling_order_action_status", create_type=False),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "kind", name="uq_bling_order_actions_order_kind"),
    )
    op.create_index("ix_bling_order_actions_order_id", "bling_order_actions", ["order_id"])
    op.create_index(
        "ix_bling_order_actions_pending_retry",
        "bling_order_actions",
        ["next_retry_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_bling_order_actions_pending_retry", table_name="bling_order_actions")
    op.drop_index("ix_bling_order_actions_order_id", table_name="bling_order_actions")
    op.drop_table("bling_order_actions")
    postgresql.ENUM(name="bling_order_action_status").drop(op.get_bind())
    postgresql.ENUM(name="bling_order_action_kind").drop(op.get_bind())
    op.drop_constraint("uq_orders_bling_order_id", "orders", type_="unique")
    for col in (
        "stock_cancel_reason",
        "bling_stock_reversed_at",
        "bling_stock_posted_at",
        "bling_situation_id",
        "bling_order_created_at",
        "bling_order_number",
        "bling_order_id",
    ):
        op.drop_column("orders", col)
    op.drop_column("stock_reservations", "bling_reflected_at")
    op.drop_column("product_variants", "stock_read_at")
