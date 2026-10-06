"""store the last posts overview visit on each user

Revision ID: h1c2d3e4f5a6
Revises: g0b1c2d3e4f5
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'h1c2d3e4f5a6'
down_revision = 'g0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('posts_index_last_seen_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_users_posts_index_last_seen_at', ['posts_index_last_seen_at'], unique=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_posts_index_last_seen_at')
        batch_op.drop_column('posts_index_last_seen_at')
