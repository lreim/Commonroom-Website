"""add session token to page visits

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-13 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('page_visits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_token', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_page_visits_session_token'),
            ['session_token'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('page_visits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_visits_session_token'))
        batch_op.drop_column('session_token')
