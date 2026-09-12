"""add OIDC subject to users

Revision ID: c4a1d9e72f06
Revises: 8b3f5e02cd41
Create Date: 2026-09-12 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4a1d9e72f06'
down_revision = '8b3f5e02cd41'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('oidc_sub', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('uq_users_oidc_sub', ['oidc_sub'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_oidc_sub', type_='unique')
        batch_op.drop_column('oidc_sub')
