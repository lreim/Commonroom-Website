"""add versioned privacy-safe analytics fields to page visits

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('page_visits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tracking_version', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('acquisition_source', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('acquisition_medium', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('acquisition_campaign', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('referrer_domain', sa.String(length=255), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_page_visits_tracking_version'),
            ['tracking_version'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_page_visits_acquisition_source'),
            ['acquisition_source'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_page_visits_acquisition_medium'),
            ['acquisition_medium'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('page_visits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_visits_acquisition_medium'))
        batch_op.drop_index(batch_op.f('ix_page_visits_acquisition_source'))
        batch_op.drop_index(batch_op.f('ix_page_visits_tracking_version'))
        batch_op.drop_column('referrer_domain')
        batch_op.drop_column('acquisition_campaign')
        batch_op.drop_column('acquisition_medium')
        batch_op.drop_column('acquisition_source')
        batch_op.drop_column('tracking_version')
