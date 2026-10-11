"""archive Sunday Check-in posts
Revision ID: i2d3e4f5a6b7
Revises: h1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa
revision='i2d3e4f5a6b7'
down_revision='h1c2d3e4f5a6'
branch_labels=None
depends_on=None
def upgrade():
    with op.batch_alter_table('posts') as batch_op:
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index('ix_posts_is_archived', ['is_archived'], unique=False)
def downgrade():
    with op.batch_alter_table('posts') as batch_op:
        batch_op.drop_index('ix_posts_is_archived')
        batch_op.drop_column('is_archived')
