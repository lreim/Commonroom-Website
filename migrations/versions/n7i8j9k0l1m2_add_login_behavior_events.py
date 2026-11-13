"""add login behavior events and exit metadata

Revision ID: n7i8j9k0l1m2
Revises: m6h7i8j9k0l1
"""
from alembic import op
import sqlalchemy as sa

revision = 'n7i8j9k0l1m2'
down_revision = 'm6h7i8j9k0l1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('auth_funnel_events', sa.Column('exit_method', sa.String(length=32), nullable=True))
    op.add_column('auth_funnel_events', sa.Column('page_key', sa.String(length=16), nullable=True))
    op.add_column('auth_funnel_events', sa.Column('duration_seconds', sa.Integer(), nullable=True))
    op.add_column('auth_funnel_events', sa.Column('destination_path', sa.String(length=255), nullable=True))
    op.add_column('auth_funnel_events', sa.Column('referrer_path', sa.String(length=255), nullable=True))
    op.create_index('ix_auth_funnel_events_exit_method', 'auth_funnel_events', ['exit_method'])
    op.create_index('ix_auth_funnel_events_page_key', 'auth_funnel_events', ['page_key'])
    op.create_table(
        'login_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_login_events_user_id', 'login_events', ['user_id'])
    op.create_index('ix_login_events_created_at', 'login_events', ['created_at'])


def downgrade():
    op.drop_table('login_events')
    op.drop_index('ix_auth_funnel_events_exit_method', table_name='auth_funnel_events')
    op.drop_index('ix_auth_funnel_events_page_key', table_name='auth_funnel_events')
    op.drop_column('auth_funnel_events', 'duration_seconds')
    op.drop_column('auth_funnel_events', 'page_key')
    op.drop_column('auth_funnel_events', 'referrer_path')
    op.drop_column('auth_funnel_events', 'destination_path')
    op.drop_column('auth_funnel_events', 'exit_method')
