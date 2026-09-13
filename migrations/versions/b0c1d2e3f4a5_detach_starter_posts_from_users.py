"""detach starter posts from personal user profiles

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-09-13 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    posts = sa.table(
        'posts',
        sa.column('author_id', sa.Integer()),
        sa.column('is_starter', sa.Boolean()),
    )
    op.execute(
        posts.update()
        .where(posts.c.is_starter.is_(True))
        .values(author_id=None)
    )


def downgrade():
    # The former personal author cannot be reconstructed safely.
    pass
