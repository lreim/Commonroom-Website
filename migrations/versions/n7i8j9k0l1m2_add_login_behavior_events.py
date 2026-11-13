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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('auth_funnel_events')}
    for name, column in (
        ('exit_method', sa.Column('exit_method', sa.String(length=32), nullable=True)),
        ('page_key', sa.Column('page_key', sa.String(length=16), nullable=True)),
        ('duration_seconds', sa.Column('duration_seconds', sa.Integer(), nullable=True)),
        ('destination_path', sa.Column('destination_path', sa.String(length=255), nullable=True)),
        ('referrer_path', sa.Column('referrer_path', sa.String(length=255), nullable=True)),
    ):
        if name not in columns:
            op.add_column('auth_funnel_events', column)
    existing_indexes = {index['name'] for index in inspector.get_indexes('auth_funnel_events')}
    for name, column in (
        ('ix_auth_funnel_events_exit_method', 'exit_method'),
        ('ix_auth_funnel_events_page_key', 'page_key'),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'auth_funnel_events', [column])
    table_names = set(inspector.get_table_names())
    if 'login_events' in table_names:
        return
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
