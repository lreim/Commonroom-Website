"""add persistent login throttling

Revision ID: 9f2c1a6e8b4d
Revises: 1ad351c4af03
Create Date: 2026-08-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f2c1a6e8b4d'
down_revision = '1ad351c4af03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'failed_login_attempts',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.add_column(
            sa.Column(
                'login_locked_until',
                sa.DateTime(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'login_lockout_count',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.add_column(
            sa.Column(
                'login_lockout_window_started_at',
                sa.DateTime(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'account_locked_until',
                sa.DateTime(),
                nullable=True,
            )
        )
        batch_op.create_index(batch_op.f('ix_users_login_locked_until'), ['login_locked_until'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_account_locked_until'), ['account_locked_until'], unique=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_account_locked_until'))
        batch_op.drop_index(batch_op.f('ix_users_login_locked_until'))
        batch_op.drop_column('account_locked_until')
        batch_op.drop_column('login_lockout_window_started_at')
        batch_op.drop_column('login_lockout_count')
        batch_op.drop_column('login_locked_until')
        batch_op.drop_column('failed_login_attempts')
