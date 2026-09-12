import unittest
from unittest.mock import patch

from app import create_app, db
from app.models import ChatRequest, Role, User


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


if __name__ == '__main__':
    unittest.main()
