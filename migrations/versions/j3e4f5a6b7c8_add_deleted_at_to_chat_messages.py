"""add soft deletion timestamp to chat messages
Revision ID: j3e4f5a6b7c8
Revises: i2d3e4f5a6b7
"""
from alembic import op
import sqlalchemy as sa

revision = 'j3e4f5a6b7c8'
down_revision = 'i2d3e4f5a6b7'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_column('deleted_at')
