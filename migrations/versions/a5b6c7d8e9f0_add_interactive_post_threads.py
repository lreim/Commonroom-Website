"""add interactive post thread features

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-23 13:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'thread_status',
            sa.String(length=32),
            nullable=False,
            server_default='looking_for_replies',
        ))
        batch_op.add_column(sa.Column('reply_type', sa.String(length=32), nullable=True))

    op.create_table(
        'post_thread_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('root_post_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['root_post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id',
            'root_post_id',
            name='uq_post_thread_subscription_user_root',
        ),
    )
    op.create_index(
        op.f('ix_post_thread_subscriptions_root_post_id'),
        'post_thread_subscriptions',
        ['root_post_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_post_thread_subscriptions_user_id'),
        'post_thread_subscriptions',
        ['user_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f('ix_post_thread_subscriptions_user_id'),
        table_name='post_thread_subscriptions',
    )
    op.drop_index(
        op.f('ix_post_thread_subscriptions_root_post_id'),
        table_name='post_thread_subscriptions',
    )
    op.drop_table('post_thread_subscriptions')

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_column('reply_type')
        batch_op.drop_column('thread_status')
