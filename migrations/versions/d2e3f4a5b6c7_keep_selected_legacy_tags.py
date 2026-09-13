"""keep selected legacy tags in public tag library

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-14 01:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


TAG_NAMES = (
    'academic pressure',
    'burnout',
    'depressive thoughts',
    'finals pressure',
    'motivation',
    'panic feelings',
    'stress management',
    'study strategy',
)


def upgrade():
    connection = op.get_bind()
    existing_names = {
        row[0] for row in connection.execute(sa.text('SELECT name FROM tags')).fetchall()
    }
    missing_names = [name for name in TAG_NAMES if name not in existing_names]
    if missing_names:
        tags = sa.table('tags', sa.column('name', sa.String(length=64)))
        op.bulk_insert(tags, [{'name': name} for name in missing_names])


def downgrade():
    # Keep tag data and user associations intact when rolling back.
    pass
