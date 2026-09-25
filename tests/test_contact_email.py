import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app import create_app, db
from app.models import ChatRequest, Conversation, Role, User


class ContactEmailTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False, AUTH_MODE='legacy')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, email, username, contact_email=None):
        user = User(
            email=email,
            contact_email=contact_email,
            username=username,
            password='Password123',
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def _login(self, email):
        response = self.client.post(
            '/auth/login',
            data={'email': email, 'password': 'Password123'},
        )
        self.assertEqual(response.status_code, 302)

    def _create_pending_chat_request(self):
        requester = self._create_user(
            'requester@ethz.ch',
            'requester',
            contact_email='sender@example.org',
        )
        requested = self._create_user(
            'requested@ethz.ch',
            'requested',
            contact_email='recipient@example.net',
        )
        chat_request = ChatRequest(
            requester_id=requester.id,
            requested_id=requested.id,
            message='A private request message',
        )
        db.session.add(chat_request)
        db.session.commit()
        return requester, requested, chat_request

    def test_optional_contact_email_can_be_saved_and_removed(self):
        user = self._create_user('login@ethz.ch', 'contact-profile')
        self._login(user.email)

        response = self.client.post(
            '/edit-profile',
            data={
                'contact_email': '  Private.Contact@example.org  ',
                'about_me': '',
                'funny_fact': '',
                'tags': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(User, user.id).contact_email, 'private.contact@example.org')

        response = self.client.post(
            '/edit-profile',
            data={
                'contact_email': '',
                'about_me': '',
                'funny_fact': '',
                'tags': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(User, user.id).contact_email)

    def test_chat_request_without_contact_email_redirects_to_profile(self):
        requester = self._create_user('requester@ethz.ch', 'requester')
        requested = self._create_user(
            'requested@ethz.ch',
            'requested',
            contact_email='requested@example.org',
        )
        self._login(requester.email)

        response = self.client.post(
            '/chat/request',
            data={'requested_user_id': requested.id, 'message': 'Could we talk?'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/edit-profile?chat_required=1#contact-email'))
        self.assertEqual(ChatRequest.query.count(), 0)

    def test_chat_request_uses_private_contact_email(self):
        requester = self._create_user(
            'requester@ethz.ch',
            'requester',
            contact_email='sender@example.org',
        )
        requested = self._create_user(
            'requested@ethz.ch',
            'requested',
            contact_email='recipient@example.net',
        )
        self._login(requester.email)

        with patch('app.chat.views.send_email') as send_email:
            response = self.client.post(
                '/chat/request',
                data={'requested_user_id': requested.id, 'message': 'Could we talk?'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ChatRequest.query.count(), 1)
        self.assertEqual(send_email.call_args.args[0], 'recipient@example.net')

    def test_profile_chat_button_points_to_contact_email_setup(self):
        requester = self._create_user('requester@ethz.ch', 'requester')
        requested = self._create_user(
            'requested@ethz.ch',
            'requested',
            contact_email='recipient@example.net',
        )
        self._login(requester.email)

        response = self.client.get(f'/user/{requested.username}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-has-contact-email="false"', response.data)
        self.assertIn(b'/edit-profile?chat_required=1#contact-email', response.data)

    def test_existing_chat_detail_renders_user_link(self):
        requester = self._create_user('requester@ethz.ch', 'requester')
        requested = self._create_user('requested@ethz.ch', 'requested')
        conversation = Conversation(
            user_a_id=min(requester.id, requested.id),
            user_b_id=max(requester.id, requested.id),
        )
        db.session.add(conversation)
        db.session.commit()
        self._login(requester.email)

        response = self.client.get(f'/chat/{conversation.id}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Chat with', response.data)
        self.assertIn(b'requested', response.data)

    def test_email_response_links_require_login_before_showing_request(self):
        _, _, chat_request = self._create_pending_chat_request()

        for action in ('accept', 'reject'):
            token = chat_request.generate_response_token(action)
            response = self.client.get(f'/chat/request/{action}/{token}')

            self.assertEqual(response.status_code, 302)
            login_url = urlparse(response.location)
            self.assertEqual(login_url.path, '/auth/login')
            query = parse_qs(login_url.query)
            self.assertEqual(query.get('gate'), ['1'])
            self.assertEqual(
                query.get('next'),
                [f'/chat/request/{action}/{token}'],
            )
            self.assertNotIn(b'A private request message', response.data)

    def test_only_requested_account_can_review_email_response_link(self):
        requester, _, chat_request = self._create_pending_chat_request()
        token = chat_request.generate_response_token('accept')
        self._login(requester.email)

        response = self.client.get(f'/chat/request/accept/{token}')

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'A private request message', response.data)

    def test_requested_account_can_review_and_accept_after_login(self):
        requester, requested, chat_request = self._create_pending_chat_request()
        token = chat_request.generate_response_token('accept')
        self._login(requested.email)

        review = self.client.get(f'/chat/request/accept/{token}')
        accepted = self.client.post(f'/chat/request/accept/{token}')

        self.assertEqual(review.status_code, 200)
        self.assertIn(b'A private request message', review.data)
        self.assertEqual(accepted.status_code, 200)
        self.assertIn(b'Open conversation', accepted.data)
        self.assertEqual(
            db.session.get(ChatRequest, chat_request.id).status,
            ChatRequest.STATUS_ACCEPTED,
        )
        self.assertIsNotNone(Conversation.query.filter(
            Conversation.user_a_id.in_([requester.id, requested.id]),
            Conversation.user_b_id.in_([requester.id, requested.id]),
        ).first())


if __name__ == '__main__':
    unittest.main()
