"""Track profile reminder funnel events."""
from alembic import op
import sqlalchemy as sa
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None
def upgrade():
    op.create_table('profile_nudge_events', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False), sa.Column('event_type', sa.String(24), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    for name, column in [('user_id','user_id'),('event_type','event_type'),('created_at','created_at')]: op.create_index('ix_profile_nudge_events_'+name, 'profile_nudge_events', [column])
def downgrade():
    op.drop_table('profile_nudge_events')
