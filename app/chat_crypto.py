import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app
from sqlalchemy.types import Text, TypeDecorator


CHAT_CIPHERTEXT_PREFIX = "cr-chat:v1:"
CHAT_ENCRYPTION_KEY_BYTES = 32


def decode_chat_encryption_key(encoded_key):
    if not encoded_key:
        raise RuntimeError("CHAT_ENCRYPTION_KEY must be configured.")
    try:
        key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise RuntimeError("CHAT_ENCRYPTION_KEY must be URL-safe base64.") from exc
    if len(key) != CHAT_ENCRYPTION_KEY_BYTES:
        raise RuntimeError("CHAT_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return key


def validate_chat_encryption_key(encoded_key):
    decode_chat_encryption_key(encoded_key)


def _aad(purpose):
    return f"commonroom:{purpose}:v1".encode("utf-8")


def encrypt_chat_text(value, purpose, encoded_key=None):
    if value is None:
        return None
    key = decode_chat_encryption_key(
        encoded_key or current_app.config.get("CHAT_ENCRYPTION_KEY")
    )
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        value.encode("utf-8"),
        _aad(purpose),
    )
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return CHAT_CIPHERTEXT_PREFIX + payload


def decrypt_chat_text(value, purpose, encoded_key=None):
    if value is None or not value.startswith(CHAT_CIPHERTEXT_PREFIX):
        # This compatibility path is required during a rolling migration of
        # existing plaintext rows. The data migration encrypts every row.
        return value
    key = decode_chat_encryption_key(
        encoded_key or current_app.config.get("CHAT_ENCRYPTION_KEY")
    )
    try:
        payload = base64.urlsafe_b64decode(
            value[len(CHAT_CIPHERTEXT_PREFIX):].encode("ascii")
        )
        nonce, ciphertext = payload[:12], payload[12:]
        if len(nonce) != 12 or not ciphertext:
            raise ValueError
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, _aad(purpose))
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Stored chat content could not be decrypted.") from exc


class EncryptedChatText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, purpose, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        return encrypt_chat_text(value, self.purpose)

    def process_result_value(self, value, dialect):
        return decrypt_chat_text(value, self.purpose)
