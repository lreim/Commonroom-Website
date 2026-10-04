"""Add responses for Sunday check-in starter posts."""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sunday_checkin_responses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id'), nullable=False),
        sa.Column('choice', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('visitor_token', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_sunday_checkin_post_user'),
    )
    op.create_index('ix_sunday_checkin_responses_post_id', 'sunday_checkin_responses', ['post_id'])
    op.create_index('ix_sunday_checkin_responses_user_id', 'sunday_checkin_responses', ['user_id'])
    op.create_index('ix_sunday_checkin_responses_visitor_token', 'sunday_checkin_responses', ['visitor_token'])


def downgrade():
    op.drop_index('ix_sunday_checkin_responses_visitor_token', table_name='sunday_checkin_responses')
    op.drop_index('ix_sunday_checkin_responses_user_id', table_name='sunday_checkin_responses')
    op.drop_index('ix_sunday_checkin_responses_post_id', table_name='sunday_checkin_responses')
    op.drop_table('sunday_checkin_responses')
