"""add edited timestamp to posts

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-13 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edited_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_column('edited_at')
