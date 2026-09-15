"""add per-user post thread visit state

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'post_thread_visits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('root_post_id', sa.Integer(), nullable=False),
        sa.Column('last_visited_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['root_post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id',
            'root_post_id',
            name='uq_post_thread_visit_user_root',
        ),
    )
    op.create_index(
        op.f('ix_post_thread_visits_root_post_id'),
        'post_thread_visits',
        ['root_post_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_post_thread_visits_user_id'),
        'post_thread_visits',
        ['user_id'],
        unique=False,
    )

    # Existing discussions start as read so deploying this feature does not
    # create a backlog of historical notifications for every account.
    op.execute(
        """
        WITH RECURSIVE post_tree(post_id, root_post_id) AS (
            SELECT id, id
            FROM posts
            WHERE parent_id IS NULL
            UNION ALL
            SELECT child.id, post_tree.root_post_id
            FROM posts AS child
            JOIN post_tree ON child.parent_id = post_tree.post_id
        )
        INSERT INTO post_thread_visits (user_id, root_post_id, last_visited_at)
        SELECT DISTINCT posts.author_id, post_tree.root_post_id, CURRENT_TIMESTAMP
        FROM posts
        JOIN post_tree ON post_tree.post_id = posts.id
        WHERE posts.author_id IS NOT NULL
        """
    )


def downgrade():
    op.drop_index(
        op.f('ix_post_thread_visits_user_id'),
        table_name='post_thread_visits',
    )
    op.drop_index(
        op.f('ix_post_thread_visits_root_post_id'),
        table_name='post_thread_visits',
    )
    op.drop_table('post_thread_visits')
