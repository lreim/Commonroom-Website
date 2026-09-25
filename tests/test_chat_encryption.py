import unittest

from sqlalchemy import text

from app import create_app, db
from app.chat_crypto import CHAT_CIPHERTEXT_PREFIX
from app.models import ChatRequest, Conversation, Message, User


class ChatEncryptionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        self.first_user = User(
            email='first@example.org',
            username='first-user',
            password='Password123',
            confirmed=True,
        )
        self.second_user = User(
            email='second@example.org',
            username='second-user',
            password='Password123',
            confirmed=True,
        )
        db.session.add_all([self.first_user, self.second_user])
        db.session.flush()
        self.conversation = Conversation(
            user_a_id=self.first_user.id,
            user_b_id=self.second_user.id,
        )
        db.session.add(self.conversation)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_message_body_is_encrypted_at_rest_and_decrypted_for_application(self):
        plaintext = 'This should not be readable in SQLite.'
        message = Message(
            conversation_id=self.conversation.id,
            author_id=self.first_user.id,
            body=plaintext,
        )
        db.session.add(message)
        db.session.commit()

        stored_value = db.session.execute(
            text('SELECT body FROM messages WHERE id = :id'),
            {'id': message.id},
        ).scalar_one()

        self.assertTrue(stored_value.startswith(CHAT_CIPHERTEXT_PREFIX))
        self.assertNotIn(plaintext, stored_value)
        db.session.expire_all()
        self.assertEqual(db.session.get(Message, message.id).body, plaintext)

    def test_chat_request_text_is_encrypted_at_rest(self):
        plaintext = 'Could we talk after the lecture?'
        chat_request = ChatRequest(
            requester_id=self.first_user.id,
            requested_id=self.second_user.id,
            message=plaintext,
        )
        db.session.add(chat_request)
        db.session.commit()

        stored_value = db.session.execute(
            text('SELECT message FROM chat_requests WHERE id = :id'),
            {'id': chat_request.id},
        ).scalar_one()

        self.assertTrue(stored_value.startswith(CHAT_CIPHERTEXT_PREFIX))
        self.assertNotIn(plaintext, stored_value)
        db.session.expire_all()
        self.assertEqual(
            db.session.get(ChatRequest, chat_request.id).message,
            plaintext,
        )

    def test_equal_messages_use_different_nonces(self):
        messages = [
            Message(
                conversation_id=self.conversation.id,
                author_id=self.first_user.id,
                body='Same text',
            ),
            Message(
                conversation_id=self.conversation.id,
                author_id=self.first_user.id,
                body='Same text',
            ),
        ]
        db.session.add_all(messages)
        db.session.commit()

        stored_values = db.session.execute(
            text('SELECT body FROM messages ORDER BY id')
        ).scalars().all()

        self.assertEqual(len(stored_values), 2)
        self.assertNotEqual(stored_values[0], stored_values[1])


if __name__ == '__main__':
    unittest.main()
