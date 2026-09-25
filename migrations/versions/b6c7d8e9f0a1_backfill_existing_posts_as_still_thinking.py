"""backfill existing post threads as still thinking

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-09-25 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    # Thread status belongs to the original post, not to its replies.
    op.execute(
        sa.text(
            """
            UPDATE posts
            SET thread_status = 'still_thinking'
            WHERE parent_id IS NULL
            """
        )
    )


def downgrade():
    # This is a one-time data backfill. Reverting it automatically could
    # overwrite a status that a user selected after the migration ran.
    pass
