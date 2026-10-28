"""store_settings

Revision ID: a7c3e91b4d20
Revises: efccebc32a0f
Create Date: 2026-10-27 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e91b4d20"
down_revision: Union[str, Sequence[str], None] = "efccebc32a0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "store_settings",
        sa.Column("id", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("theme", sa.String(length=50), nullable=False),
        sa.Column("brand_color", sa.String(length=7), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_store_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("store_settings")
