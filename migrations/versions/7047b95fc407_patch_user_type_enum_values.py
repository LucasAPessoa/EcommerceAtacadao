"""patch user type enum values

Revision ID: 7047b95fc407
Revises: f0d3a031ca4d
Create Date: 2026-07-05 14:16:56.569235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7047b95fc407'
down_revision: Union[str, Sequence[str], None] = 'f0d3a031ca4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE usertypeenum RENAME VALUE 'RETAIL' TO 'INDIVIDUAL'")
    op.execute("ALTER TYPE usertypeenum RENAME VALUE 'WHOLESALE' TO 'COMPANY'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
