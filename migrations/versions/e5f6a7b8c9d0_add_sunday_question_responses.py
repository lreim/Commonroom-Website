"""Store one Sunday check-in response per question."""
from alembic import op
import sqlalchemy as sa
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None
def upgrade():
    op.add_column('sunday_checkin_responses', sa.Column('question', sa.String(length=32), nullable=True))
    op.execute("UPDATE sunday_checkin_responses SET question = 'moment' WHERE question IS NULL")
    with op.batch_alter_table('sunday_checkin_responses') as batch:
        batch.alter_column('question', nullable=False)
        batch.drop_constraint('uq_sunday_checkin_post_user', type_='unique')
        batch.create_unique_constraint('uq_sunday_checkin_post_question_user', ['post_id', 'question', 'user_id'])
def downgrade():
    with op.batch_alter_table('sunday_checkin_responses') as batch:
        batch.drop_constraint('uq_sunday_checkin_post_question_user', type_='unique')
        batch.create_unique_constraint('uq_sunday_checkin_post_user', ['post_id', 'user_id'])
        batch.drop_column('question')
