"""add anonymous authentication funnel attempts

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-15 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auth_funnel_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attempt_token', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('authenticated_at', sa.DateTime(), nullable=True),
        sa.Column('profile_required_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_auth_funnel_attempts_action'), 'auth_funnel_attempts', ['action'], unique=False)
    op.create_index(op.f('ix_auth_funnel_attempts_attempt_token'), 'auth_funnel_attempts', ['attempt_token'], unique=True)
    op.create_index(op.f('ix_auth_funnel_attempts_completed_at'), 'auth_funnel_attempts', ['completed_at'], unique=False)
    op.create_index(op.f('ix_auth_funnel_attempts_started_at'), 'auth_funnel_attempts', ['started_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_auth_funnel_attempts_started_at'), table_name='auth_funnel_attempts')
    op.drop_index(op.f('ix_auth_funnel_attempts_completed_at'), table_name='auth_funnel_attempts')
    op.drop_index(op.f('ix_auth_funnel_attempts_attempt_token'), table_name='auth_funnel_attempts')
    op.drop_index(op.f('ix_auth_funnel_attempts_action'), table_name='auth_funnel_attempts')
    op.drop_table('auth_funnel_attempts')
