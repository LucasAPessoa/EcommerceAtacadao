"""merge user detail tables into users

Revision ID: 8f3c0d9a6b21
Revises: 22f3d01488d4
Create Date: 2026-06-30 23:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8f3c0d9a6b21'
down_revision: Union[str, Sequence[str], None] = '22f3d01488d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.String(length=150), nullable=True))
    op.add_column('users', sa.Column('cpf', sa.String(length=11), nullable=True))
    op.add_column('users', sa.Column('cnpj', sa.String(length=14), nullable=True))
    op.add_column('users', sa.Column('corporate_name', sa.String(length=150), nullable=True))
    op.add_column('users', sa.Column('ie', sa.String(length=20), nullable=True))

    op.execute(
        """
        UPDATE users AS users
        SET full_name = users_cpf.full_name,
            cpf = users_cpf.cpf,
            user_type = 'individual'
        FROM users_cpf
        WHERE users.id = users_cpf.id
        """
    )
    op.execute(
        """
        UPDATE users AS users
        SET cnpj = users_cnpj.cnpj,
            corporate_name = users_cnpj.corporate_name,
            ie = users_cnpj.ie,
            user_type = 'company'
        FROM users_cnpj
        WHERE users.id = users_cnpj.id
        """
    )

    op.execute(
        """
        UPDATE users
        SET user_type = 'individual'
        WHERE user_type IN ('client', 'user', 'cpf')
        """
    )
    op.execute(
        """
        UPDATE users
        SET user_type = 'company'
        WHERE user_type = 'cnpj'
        """
    )

    op.create_unique_constraint('uq_users_cpf', 'users', ['cpf'])
    op.create_unique_constraint('uq_users_cnpj', 'users', ['cnpj'])

    op.drop_table('users_cpf')
    op.drop_table('users_cnpj')


def downgrade() -> None:
    op.create_table(
        'users_cnpj',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('corporate_name', sa.String(length=150), nullable=False),
        sa.Column('ie', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cnpj')
    )
    op.create_table(
        'users_cpf',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cpf', sa.String(length=11), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cpf')
    )

    op.execute(
        """
        INSERT INTO users_cpf (id, cpf, full_name)
        SELECT id, cpf, full_name
        FROM users
        WHERE user_type = 'individual' AND cpf IS NOT NULL AND full_name IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO users_cnpj (id, cnpj, corporate_name, ie)
        SELECT id, cnpj, corporate_name, ie
        FROM users
        WHERE user_type = 'company' AND cnpj IS NOT NULL AND corporate_name IS NOT NULL
        """
    )

    op.drop_constraint('uq_users_cnpj', 'users', type_='unique')
    op.drop_constraint('uq_users_cpf', 'users', type_='unique')
    op.drop_column('users', 'ie')
    op.drop_column('users', 'corporate_name')
    op.drop_column('users', 'cnpj')
    op.drop_column('users', 'cpf')
    op.drop_column('users', 'full_name')
