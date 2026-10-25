"""add visit purpose survey events

Revision ID: l5g6h7i8j9k0
Revises: k4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

revision = 'l5g6h7i8j9k0'
down_revision = 'k4f5a6b7c8d9'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'visit_purpose_survey_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('visitor_token', sa.String(length=64), nullable=True),
        sa.Column('audience', sa.String(length=24), nullable=False),
        sa.Column('event_type', sa.String(length=24), nullable=False),
        sa.Column('choice', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_visit_purpose_survey_events_user_id', 'visit_purpose_survey_events', ['user_id'])
    op.create_index('ix_visit_purpose_survey_events_visitor_token', 'visit_purpose_survey_events', ['visitor_token'])
    op.create_index('ix_visit_purpose_survey_events_audience', 'visit_purpose_survey_events', ['audience'])
    op.create_index('ix_visit_purpose_survey_events_event_type', 'visit_purpose_survey_events', ['event_type'])
    op.create_index('ix_visit_purpose_survey_events_created_at', 'visit_purpose_survey_events', ['created_at'])

def downgrade():
    op.drop_table('visit_purpose_survey_events')
