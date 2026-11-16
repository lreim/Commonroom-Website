"""add topic categories to posts

Revision ID: o8j9k0l1m2n3
Revises: n7i8j9k0l1m2
"""
from alembic import op
import sqlalchemy as sa

revision = 'o8j9k0l1m2n3'
down_revision = 'n7i8j9k0l1m2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('posts')}
    if 'category' not in columns:
        op.add_column('posts', sa.Column('category', sa.String(length=32), nullable=True, server_default='other'))
        op.execute("UPDATE posts SET category = 'other' WHERE category IS NULL")
        op.alter_column('posts', 'category', nullable=False, server_default=None)
    indexes = {index['name'] for index in inspector.get_indexes('posts')}
    if 'ix_posts_category' not in indexes:
        op.create_index('ix_posts_category', 'posts', ['category'])


def downgrade():
    op.drop_index('ix_posts_category', table_name='posts')
    op.drop_column('posts', 'category')
