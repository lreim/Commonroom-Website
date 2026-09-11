"""move support tags to profile labels

Revision ID: 8b3f5e02cd41
Revises: 7a2e4d91bc30
Create Date: 2026-09-11 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8b3f5e02cd41'
down_revision = '7a2e4d91bc30'
branch_labels = None
depends_on = None


LABEL_MAP = {
    'listener': ('happy_to_share_experience',),
    'peer_support': ('currently_dealing_with_this',),
    'practical_advice': ('happy_to_listen',),
    'all': (
        'been_through_this',
        'currently_dealing_with_this',
        'happy_to_listen',
        'happy_to_share_experience',
    ),
}


def _map_labels(value):
    mapped = []
    for old_label in (value or '').split(','):
        old_label = old_label.strip()
        for new_label in LABEL_MAP.get(old_label, ()):
            if new_label not in mapped:
                mapped.append(new_label)
    return ','.join(mapped) or None


def upgrade():
    connection = op.get_bind()
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'profile_label',
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=True,
        )

    rows = connection.execute(
        sa.text('SELECT id, profile_label FROM users WHERE profile_label IS NOT NULL')
    ).fetchall()
    for user_id, profile_label in rows:
        connection.execute(
            sa.text('UPDATE users SET profile_label = :profile_label WHERE id = :user_id'),
            {'profile_label': _map_labels(profile_label), 'user_id': user_id},
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'profile_label',
            existing_type=sa.String(length=128),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
