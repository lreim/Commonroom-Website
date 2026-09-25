"""encrypt stored chat content

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-25 18:10:00.000000

"""
import os

from alembic import op
import sqlalchemy as sa

from app.chat_crypto import (
    CHAT_CIPHERTEXT_PREFIX,
    decrypt_chat_text,
    encrypt_chat_text,
    validate_chat_encryption_key,
)


revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def _configured_key():
    encoded_key = os.environ.get('CHAT_ENCRYPTION_KEY')
    validate_chat_encryption_key(encoded_key)
    return encoded_key


def _transform_rows(table_name, column_name, purpose, transform):
    connection = op.get_bind()
    table = sa.table(
        table_name,
        sa.column('id', sa.Integer),
        sa.column(column_name, sa.Text),
    )
    rows = connection.execute(
        sa.select(table.c.id, table.c[column_name])
    ).all()
    encoded_key = _configured_key()

    for row_id, stored_value in rows:
        new_value = transform(stored_value, purpose, encoded_key)
        connection.execute(
            table.update()
            .where(table.c.id == row_id)
            .values({column_name: new_value})
        )


def _encrypt_unless_already_encrypted(value, purpose, encoded_key):
    if value is None or value.startswith(CHAT_CIPHERTEXT_PREFIX):
        return value
    return encrypt_chat_text(value, purpose, encoded_key)


def upgrade():
    _transform_rows(
        'messages',
        'body',
        'message',
        _encrypt_unless_already_encrypted,
    )
    _transform_rows(
        'chat_requests',
        'message',
        'chat-request',
        _encrypt_unless_already_encrypted,
    )


def downgrade():
    _transform_rows(
        'messages',
        'body',
        'message',
        decrypt_chat_text,
    )
    _transform_rows(
        'chat_requests',
        'message',
        'chat-request',
        decrypt_chat_text,
    )
