"""seed canonical user role

Revision ID: a12f4ce980bd
Revises: 4b7e2c9d1a10
Create Date: 2026-10-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a12f4ce980bd"
down_revision: Union[str, Sequence[str], None] = "4b7e2c9d1a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Garante a role mínima para cadastros públicos, inclusive sem seed."""
    op.execute(
        sa.text(
            """
            INSERT INTO roles (id, name, created_at, updated_at)
            VALUES (
                'a4c2d6b0-6e1d-4ef8-93b3-91bd1e001001',
                'user',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (name) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    """Preserva a role para não invalidar usuários já cadastrados."""
