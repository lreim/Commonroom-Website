"""add vegan and neurodivergent profile tags

Revision ID: g0b1c2d3e4f5
Revises: f8a9b0c1d2e3
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'g0b1c2d3e4f5'
down_revision = ('f6a7b8c9d0e1', 'f8a9b0c1d2e3')
branch_labels = None
depends_on = None


def upgrade():
    tags = sa.table('tags', sa.column('name', sa.String(length=64)))
    connection = op.get_bind()
    for name in ('vegan', 'neurodivergent'):
        if connection.execute(sa.select(tags.c.name).where(tags.c.name == name)).first() is None:
            connection.execute(tags.insert().values(name=name))


def downgrade():
    tags = sa.table('tags', sa.column('name', sa.String(length=64)))
    connection = op.get_bind()
    connection.execute(tags.delete().where(tags.c.name.in_(['vegan', 'neurodivergent'])))
