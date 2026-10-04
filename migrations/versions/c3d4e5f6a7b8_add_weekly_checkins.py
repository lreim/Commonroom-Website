"""Add weekly check-in responses."""
from alembic import op
import sqlalchemy as sa
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None
def upgrade():
    op.create_table('weekly_checkin_responses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('week_key', sa.String(16), nullable=False),
        sa.Column('choice', sa.String(32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('visitor_token', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']))
    op.create_index('ix_weekly_checkin_responses_week_key', 'weekly_checkin_responses', ['week_key'])
    op.create_index('ix_weekly_checkin_responses_user_id', 'weekly_checkin_responses', ['user_id'])
    op.create_index('ix_weekly_checkin_responses_visitor_token', 'weekly_checkin_responses', ['visitor_token'])
def downgrade():
    op.drop_table('weekly_checkin_responses')
