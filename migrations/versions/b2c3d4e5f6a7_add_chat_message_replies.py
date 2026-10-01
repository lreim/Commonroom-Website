"""Add direct replies between private chat messages."""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('reply_to_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_messages_reply_to_id', 'messages', ['reply_to_id'], ['id'])
        batch_op.create_index('ix_messages_reply_to_id', ['reply_to_id'])

def downgrade():
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_index('ix_messages_reply_to_id')
        batch_op.drop_constraint('fk_messages_reply_to_id', type_='foreignkey')
        batch_op.drop_column('reply_to_id')
