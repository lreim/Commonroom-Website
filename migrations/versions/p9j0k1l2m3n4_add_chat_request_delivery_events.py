"""track chat requests blocked by missing recipient email

Revision ID: p9j0k1l2m3n4
Revises: o8j9k0l1m2n3
"""
from alembic import op
import sqlalchemy as sa

revision = "p9j0k1l2m3n4"
down_revision = "o8j9k0l1m2n3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_request_analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_request_analytics_events_event_type", "chat_request_analytics_events", ["event_type"])
    op.create_index("ix_chat_request_analytics_events_created_at", "chat_request_analytics_events", ["created_at"])


def downgrade():
    op.drop_table("chat_request_analytics_events")
