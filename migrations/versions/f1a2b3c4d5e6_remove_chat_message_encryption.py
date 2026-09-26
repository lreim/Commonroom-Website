"""Decrypt stored chat text and return chat fields to plain text."""
import os

from alembic import op
import sqlalchemy as sa

from app.chat_crypto import CHAT_CIPHERTEXT_PREFIX, decrypt_chat_text, encrypt_chat_text


revision = 'f1a2b3c4d5e6'
down_revision = 'e0f1a2b3c4d5'
branch_labels = None
depends_on = None


def _transform(table_name, column_name, purpose, transform):
    connection = op.get_bind()
    table = sa.table(table_name, sa.column('id', sa.Integer), sa.column(column_name, sa.Text))
    rows = connection.execute(sa.select(table.c.id, table.c[column_name])).all()
    encoded_key = os.environ.get('CHAT_ENCRYPTION_KEY')
    for row_id, value in rows:
        if value is None:
            continue
        connection.execute(
            table.update().where(table.c.id == row_id).values({column_name: transform(value, purpose, encoded_key)})
        )


def _decrypt(value, purpose, encoded_key):
    if not value.startswith(CHAT_CIPHERTEXT_PREFIX):
        return value
    if not encoded_key:
        raise RuntimeError(
            'Encrypted chat data exists, but CHAT_ENCRYPTION_KEY is not configured. '
            'Set the original key and rerun this migration.'
        )
    return decrypt_chat_text(value, purpose, encoded_key)


def _encrypt(value, purpose, encoded_key):
    if value is None or value.startswith(CHAT_CIPHERTEXT_PREFIX):
        return value
    if not encoded_key:
        raise RuntimeError('CHAT_ENCRYPTION_KEY is required to reverse this migration.')
    return encrypt_chat_text(value, purpose, encoded_key)


def upgrade():
    _transform('messages', 'body', 'message', _decrypt)
    _transform('chat_requests', 'message', 'chat-request', _decrypt)
    _transform('content_reports', 'body', 'report', _decrypt)


def downgrade():
    _transform('messages', 'body', 'message', _encrypt)
    _transform('chat_requests', 'message', 'chat-request', _encrypt)
    _transform('content_reports', 'body', 'report', _encrypt)
