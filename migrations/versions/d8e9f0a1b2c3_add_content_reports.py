"""Add private content reports and email delivery tracking."""
from alembic import op
import sqlalchemy as sa

revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'content_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('target_type', sa.String(16), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('reporter_id', sa.Integer(), nullable=False),
        sa.Column('reporter_username', sa.String(64), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('author_username', sa.String(64), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('email_sent_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('reporter_id', 'target_type', 'target_id', name='uq_content_report_reporter_target'),
        sa.CheckConstraint("target_type IN ('post', 'message')", name='ck_content_report_target_type'),
    )
    op.create_index('ix_content_reports_created_at', 'content_reports', ['created_at'])
    op.create_index('ix_content_report_target', 'content_reports', ['target_type', 'target_id'])


def downgrade():
    op.drop_table('content_reports')
