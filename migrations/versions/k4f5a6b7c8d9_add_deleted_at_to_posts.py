"""add soft deletion timestamp to posts
Revision ID: k4f5a6b7c8d9
Revises: j3e4f5a6b7c8
"""
from alembic import op
import sqlalchemy as sa

revision = 'k4f5a6b7c8d9'
down_revision = 'j3e4f5a6b7c8'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('posts') as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table('posts') as batch_op:
        batch_op.drop_column('deleted_at')
