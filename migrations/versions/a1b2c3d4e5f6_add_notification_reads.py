"""Store notification read state per user profile.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification_reads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_key', sa.String(length=512), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'notification_key', name='uq_notification_read_user_key'),
    )
    op.create_index('ix_notification_reads_user_id', 'notification_reads', ['user_id'])


def downgrade():
    op.drop_index('ix_notification_reads_user_id', table_name='notification_reads')
    op.drop_table('notification_reads')
