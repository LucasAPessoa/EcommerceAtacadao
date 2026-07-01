"""add default roles

Revision ID: 22f3d01488d4
Revises: 0281d41070fa
Create Date: 2026-06-30 22:53:44.717101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22f3d01488d4'
down_revision: Union[str, Sequence[str], None] = '0281d41070fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert default roles
    role_table = sa.table('roles',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime)
    )
    
    from datetime import datetime
    now = datetime.utcnow()
    
    op.bulk_insert(role_table, [
        {'id': 1, 'name': 'admin', 'created_at': now, 'updated_at': now},
        {'id': 2, 'name': 'user', 'created_at': now, 'updated_at': now},
        {'id': 3, 'name': 'manager', 'created_at': now, 'updated_at': now},
    ])


def downgrade() -> None:
    # Remove the roles we added
    op.execute("DELETE FROM roles WHERE id IN (1, 2, 3)")