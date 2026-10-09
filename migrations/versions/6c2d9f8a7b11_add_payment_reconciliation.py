"""add durable payment reconciliation

Revision ID: 6c2d9f8a7b11
Revises: a12f4ce980bd
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6c2d9f8a7b11"
down_revision: Union[str, Sequence[str], None] = "a12f4ce980bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'PAYMENT_RECONCILIATION'")
    op.execute("ALTER TYPE paymentmethodenum ADD VALUE IF NOT EXISTS 'MERCADO_PAGO'")

    reconciliation_status = postgresql.ENUM(
        "PENDING",
        "IN_REVIEW",
        "RESOLVED",
        name="reconciliationstatusenum",
        create_type=False,
    )
    reconciliation_reason = postgresql.ENUM(
        "STOCK_COMMIT_FAILED",
        "CANCELED_ORDER_APPROVED",
        name="reconciliationreasonenum",
        create_type=False,
    )
    reconciliation_outcome = postgresql.ENUM(
        "FULFILLMENT_CONFIRMED", "REFUND_REQUESTED", "REFUNDED", "MANUAL_REVIEW",
        name="reconciliationoutcomeenum", create_type=False,
    )
    reconciliation_status.create(op.get_bind(), checkfirst=True)
    reconciliation_reason.create(op.get_bind(), checkfirst=True)
    reconciliation_outcome.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payment_reconciliations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("status", reconciliation_status, nullable=False),
        sa.Column("reason", reconciliation_reason, nullable=False),
        sa.Column("outcome", reconciliation_outcome),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime()),
        sa.Column("next_retry_at", sa.DateTime()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("last_error_code", sa.String(length=80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_payment_reconciliations_order"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index(
        "ix_payment_reconciliations_status", "payment_reconciliations", ["status"]
    )
    op.create_index(
        "ix_payment_reconciliations_next_retry_at", "payment_reconciliations", ["next_retry_at"]
    )
    op.add_column("refunds", sa.Column("gateway_ref_id", sa.String(length=100)))
    op.add_column("refunds", sa.Column("idempotency_key", sa.String(length=100)))
    op.add_column(
        "refunds", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("refunds", sa.Column("last_attempt_at", sa.DateTime()))
    op.add_column("refunds", sa.Column("next_retry_at", sa.DateTime()))
    op.add_column("refunds", sa.Column("last_error_code", sa.String(length=80)))
    op.create_index("ix_refunds_next_retry_at", "refunds", ["next_retry_at"])
    op.create_unique_constraint("uq_refunds_gateway_ref_id", "refunds", ["gateway_ref_id"])
    op.create_unique_constraint("uq_refunds_idempotency_key", "refunds", ["idempotency_key"])
    op.create_unique_constraint(
        "uq_transactions_gateway_ref_id", "transactions", ["gateway_ref_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_transactions_gateway_ref_id", "transactions", type_="unique")
    op.drop_index("ix_refunds_next_retry_at", table_name="refunds")
    op.drop_column("refunds", "last_error_code")
    op.drop_column("refunds", "next_retry_at")
    op.drop_column("refunds", "last_attempt_at")
    op.drop_column("refunds", "attempts")
    op.drop_constraint("uq_refunds_idempotency_key", "refunds", type_="unique")
    op.drop_constraint("uq_refunds_gateway_ref_id", "refunds", type_="unique")
    op.drop_column("refunds", "idempotency_key")
    op.drop_column("refunds", "gateway_ref_id")
    op.drop_index("ix_payment_reconciliations_next_retry_at", table_name="payment_reconciliations")
    op.drop_index("ix_payment_reconciliations_status", table_name="payment_reconciliations")
    op.drop_table("payment_reconciliations")
    postgresql.ENUM(name="reconciliationoutcomeenum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="reconciliationreasonenum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="reconciliationstatusenum").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL não permite remover valores de enum de forma segura. O downgrade
    # preserva os valores adicionados para não reescrever tabelas em produção.
