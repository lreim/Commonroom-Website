"""add auth funnel exit events

Revision ID: m6h7i8j9k0l1
Revises: l5g6h7i8j9k0
"""
from alembic import op
import sqlalchemy as sa

revision = 'm6h7i8j9k0l1'
down_revision = 'l5g6h7i8j9k0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auth_funnel_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('attempt_id', sa.Integer(), sa.ForeignKey('auth_funnel_attempts.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_auth_funnel_events_attempt_id', 'auth_funnel_events', ['attempt_id'])
    op.create_index('ix_auth_funnel_events_user_id', 'auth_funnel_events', ['user_id'])
    op.create_index('ix_auth_funnel_events_event_type', 'auth_funnel_events', ['event_type'])
    op.create_index('ix_auth_funnel_events_created_at', 'auth_funnel_events', ['created_at'])


def downgrade():
    op.drop_table('auth_funnel_events')
