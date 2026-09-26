"""Add edited timestamps to private chat messages."""
from alembic import op
import sqlalchemy as sa

revision = 'e0f1a2b3c4d5'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edited_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('edited_at')
