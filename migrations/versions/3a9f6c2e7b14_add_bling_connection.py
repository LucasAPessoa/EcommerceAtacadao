"""add bling connection

Revision ID: 3a9f6c2e7b14
Revises: c4a8e1d7f905
Create Date: 2026-10-19 00:06:45.216646

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a9f6c2e7b14"
down_revision: Union[str, Sequence[str], None] = "c4a8e1d7f905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aditiva: três tabelas novas e seus enums (criados com a tabela).
    op.create_table(
        "bling_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NOT_CONNECTED", "CONNECTED", "RECONNECT_REQUIRED", name="blingconnectionstatusenum"
            ),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(length=64), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("access_expires_at", sa.DateTime(), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("singleton", name="ck_bling_connections_singleton"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton", name="uq_bling_connections_singleton"),
    )
    op.create_table(
        "bling_authorization_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("initiated_by_user_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_table(
        "bling_connection_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "event",
            sa.Enum(
                "CONNECTED",
                "REFRESHED",
                "REFRESH_FAILED",
                "RECONNECT_REQUIRED",
                "DISCONNECTED",
                "CONNECT_REJECTED",
                name="blingconnectioneventenum",
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bling_connection_events_created_at"),
        "bling_connection_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Remove tabelas e os tipos enum do Postgres.
    op.drop_index(
        op.f("ix_bling_connection_events_created_at"), table_name="bling_connection_events"
    )
    op.drop_table("bling_connection_events")
    op.drop_table("bling_authorization_attempts")
    op.drop_table("bling_connections")
    op.execute("DROP TYPE IF EXISTS blingconnectioneventenum")
    op.execute("DROP TYPE IF EXISTS blingconnectionstatusenum")
