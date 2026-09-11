"""refresh default tag library

Revision ID: 7a2e4d91bc30
Revises: 3c7f8a2d9e10
Create Date: 2026-09-11 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7a2e4d91bc30'
down_revision = '3c7f8a2d9e10'
branch_labels = None
depends_on = None


TAG_NAMES = (
    'exam stress', 'failed an exam', 'study motivation', 'procrastination',
    'study pressure', 'overwhelmed by uni', 'study routine', 'group projects',
    'first semester', 'starting at eth', 'changing degree', 'study doubts',
    'career uncertainty', 'internship search', "master's decision", 'phd thoughts',
    'feeling lost', 'finding direction', 'making friends', 'finding your people',
    'feeling left out', 'loneliness', 'social anxiety', 'friendships',
    'friendship problems', 'enjoying being alone', 'relationships', 'breakups',
    'family pressure', 'setting boundaries', 'stress', 'overthinking', 'self doubt',
    'imposter syndrome', 'low motivation', 'feeling motivated', 'feeling overwhelmed',
    'feeling stuck', 'comparison', 'fear of failure', 'sleep', 'bad sleep schedule',
    'work life balance', 'routines', 'flatmates', 'living in zurich', 'exercise',
    'low energy', 'rest and recovery', 'body image', 'small wins', 'proud of myself',
    'good day', 'bad day', 'finally passed',
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
    # Keep tag data and user associations intact when rolling back this data migration.
    pass
