"""add catalog sync

Revision ID: 87b8656132d8
Revises: 3a9f6c2e7b14
Create Date: 2026-10-26 00:41:24.509297

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "87b8656132d8"
down_revision: Union[str, Sequence[str], None] = "3a9f6c2e7b14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aditiva: 2 tabelas (enums criados com elas), 5 colunas e image_url 255 -> 1000.
    op.create_table(
        "catalog_sync_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "trigger", sa.Enum("SCHEDULED", "MANUAL", name="catalogsynctriggerenum"), nullable=False
        ),
        sa.Column("triggered_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING",
                "SUCCESS",
                "PARTIAL",
                "FAILED",
                "SKIPPED",
                name="catalogsyncrunstatusenum",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("invocations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deactivated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blocked", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "errors", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_catalog_sync_runs_started_at"), "catalog_sync_runs", ["started_at"], unique=False
    )
    op.create_table(
        "catalog_sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("current_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "phase",
            sa.Enum(
                "IDLE",
                "CATEGORIES",
                "SCAN",
                "DETAILS",
                "STOCK",
                "FINALIZE",
                name="catalogsyncphaseenum",
            ),
            server_default="IDLE",
            nullable=False,
        ),
        sa.Column(
            "cursor", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "seen_bling_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "changed_bling_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("scan_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_complete_cycle_at", sa.DateTime(), nullable=True),
        sa.Column("last_full_detail_at", sa.DateTime(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_catalog_sync_state_singleton"),
        sa.ForeignKeyConstraint(
            ["current_run_id"],
            ["catalog_sync_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("orders", sa.Column("bling_registered_at", sa.DateTime(), nullable=True))
    op.alter_column(
        "product_images",
        "image_url",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.String(length=1000),
        existing_nullable=False,
    )
    op.add_column("product_variants", sa.Column("bling_stock_balance", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("bling_content_hash", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("bling_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Atenção: encurtar image_url falha se já houver URL com mais de 255 caracteres.
    op.drop_column("products", "bling_updated_at")
    op.drop_column("products", "bling_content_hash")
    op.drop_column("product_variants", "bling_stock_balance")
    op.alter_column(
        "product_images",
        "image_url",
        existing_type=sa.String(length=1000),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.drop_column("orders", "bling_registered_at")
    op.drop_table("catalog_sync_state")
    op.drop_index(op.f("ix_catalog_sync_runs_started_at"), table_name="catalog_sync_runs")
    op.drop_table("catalog_sync_runs")
    op.execute("DROP TYPE IF EXISTS catalogsyncphaseenum")
    op.execute("DROP TYPE IF EXISTS catalogsyncrunstatusenum")
    op.execute("DROP TYPE IF EXISTS catalogsynctriggerenum")
