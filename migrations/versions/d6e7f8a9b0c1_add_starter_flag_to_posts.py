"""add starter flag to posts

Revision ID: d6e7f8a9b0c1
Revises: c4a1d9e72f06
Create Date: 2026-09-12 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c4a1d9e72f06'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_starter', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_column('is_starter')
