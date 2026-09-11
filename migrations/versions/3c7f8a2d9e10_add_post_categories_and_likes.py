"""add post categories and likes

Revision ID: 3c7f8a2d9e10
Revises: 9f2c1a6e8b4d
Create Date: 2026-09-11 20:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3c7f8a2d9e10'
down_revision = '9f2c1a6e8b4d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('post_type', sa.String(length=16), nullable=False, server_default='relate'))
        batch_op.create_index(batch_op.f('ix_posts_post_type'), ['post_type'], unique=False)

    op.create_table(
        'post_likes',
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('post_id', 'user_id'),
    )


def downgrade():
    op.drop_table('post_likes')
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_posts_post_type'))
        batch_op.drop_column('post_type')
