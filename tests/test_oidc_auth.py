import time
import unittest
from unittest.mock import patch

from flask import redirect

from app import create_app, db
from app.auth.views import OIDC_PENDING_PROFILE_SESSION_KEY
from app.models import Role, User


class FakeEduIDClient:
    def __init__(self, token=None, callback_error=None, userinfo=None):
        self.token = token
        self.callback_error = callback_error
        self.userinfo_claims = userinfo
        self.redirect_kwargs = None

    def authorize_redirect(self, **kwargs):
        self.redirect_kwargs = kwargs
        return redirect('https://login.eduid.ch/authorize')

    def authorize_access_token(self):
        if self.callback_error:
            raise self.callback_error
        return self.token

    def userinfo(self, token):
        if self.userinfo_claims is not None:
            return self.userinfo_claims
        return token['userinfo']


class OIDCAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(
            WTF_CSRF_ENABLED=False,
            AUTH_MODE='legacy',
            OIDC_DISCOVERY_URL='https://login.eduid.ch/.well-known/openid-configuration',
            OIDC_CLIENT_ID='test-client',
            OIDC_CLIENT_SECRET='test-secret',
            OIDC_REDIRECT_URI='https://commonroom.ch/auth/eduid/callback',
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _student_token(self, subject='pairwise-subject'):
        return {
            'id_token': 'validated-by-authlib',
            'userinfo': {
                'sub': subject,
                'eduPersonAffiliation': ['student'],
            },
        }

    def _enable_oidc(self):
        self.app.config['AUTH_MODE'] = 'oidc'

    def test_legacy_mode_exposes_only_legacy_login(self):
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Forgot Password?', response.data)
        self.assertEqual(self.client.get('/auth/eduid/login').status_code, 404)
        self.assertEqual(self.client.get('/auth/eduid/callback').status_code, 404)
        self.assertEqual(self.client.get('/auth/eduid/create-profile').status_code, 404)

    def test_legacy_password_login_works_in_legacy_mode(self):
        user = User(
            email='student@ethz.ch',
            username='legacy-user',
            password='LegacyPassword1',
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()

        response = self.client.post(
            '/auth/login',
            data={
                'email': 'student@ethz.ch',
                'password': 'LegacyPassword1',
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(user.id))

    def test_oidc_mode_uses_oidc_for_normal_login(self):
        self.app.config['AUTH_MODE'] = 'oidc'
        fake_client = FakeEduIDClient()
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/login')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://login.eduid.ch/authorize')
        self.assertEqual(self.client.get('/auth/legacy/login').status_code, 404)
        self.assertEqual(
            fake_client.redirect_kwargs['redirect_uri'],
            'https://commonroom.ch/auth/eduid/callback',
        )
        self.assertTrue(fake_client.redirect_kwargs['nonce'])

    def test_existing_oidc_user_uses_flask_login_session(self):
        self._enable_oidc()
        user = User(
            username='existing-user',
            oidc_sub='existing-subject',
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        fake_client = FakeEduIDClient(token=self._student_token('existing-subject'))

        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/eduid/callback')

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(user.id))
            self.assertNotIn('id_token', client_session)
            self.assertNotIn('access_token', client_session)

    def test_new_oidc_user_is_created_only_after_profile_confirmation(self):
        self._enable_oidc()
        fake_client = FakeEduIDClient(token=self._student_token())
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/eduid/callback')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/auth/eduid/create-profile'))
        self.assertIsNone(User.query.filter_by(oidc_sub='pairwise-subject').first())

        response = self.client.post('/auth/eduid/create-profile')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/auth/eduid/welcome'))
        user = User.query.filter_by(oidc_sub='pairwise-subject').one()
        self.assertIsNone(user.email)
        self.assertIsNone(user.password_hash)
        self.assertTrue(user.confirmed)
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(user.id))
            self.assertNotIn(OIDC_PENDING_PROFILE_SESSION_KEY, client_session)

        response = self.client.get('/auth/eduid/welcome')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to CommonRoom', response.data)
        self.assertIn(user.username.encode(), response.data)

    def test_non_student_is_rejected_without_persisting_claims(self):
        self._enable_oidc()
        token = {
            'id_token': 'validated-by-authlib',
            'userinfo': {
                'sub': 'staff-subject',
                'email': 'identifying@example.org',
                'name': 'Identifying Name',
                'swissEduPersonUniqueID': 'do-not-store',
                'eduPersonAffiliation': ['staff'],
            },
        }
        with patch(
            'app.auth.views._get_eduid_client',
            return_value=FakeEduIDClient(token=token),
        ):
            response = self.client.get('/auth/eduid/callback')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.query.count(), 0)
        with self.client.session_transaction() as client_session:
            self.assertNotIn(OIDC_PENDING_PROFILE_SESSION_KEY, client_session)

    def test_invalid_oidc_response_fails_cleanly(self):
        self._enable_oidc()
        fake_client = FakeEduIDClient(token={'access_token': 'must-not-be-stored'})
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/eduid/callback')

        self.assertEqual(response.status_code, 400)
        self.assertIn(b'could not be validated', response.data)
        with self.client.session_transaction() as client_session:
            self.assertNotIn('access_token', client_session)

    def test_userinfo_subject_must_match_verified_id_token(self):
        self._enable_oidc()
        fake_client = FakeEduIDClient(
            token=self._student_token('verified-subject'),
            userinfo={
                'sub': 'different-subject',
                'eduPersonAffiliation': ['student'],
            },
        )
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/eduid/callback')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), 0)

    def test_pending_profile_subject_expires(self):
        self._enable_oidc()
        with self.client.session_transaction() as client_session:
            client_session[OIDC_PENDING_PROFILE_SESSION_KEY] = {
                'sub': 'expired-subject',
                'issued_at': int(time.time()) - 601,
            }

        response = self.client.post('/auth/eduid/create-profile')
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(User.query.filter_by(oidc_sub='expired-subject').first())

    def test_duplicate_oidc_subject_does_not_create_another_account(self):
        self._enable_oidc()
        existing_user = User(
            username='already-created',
            oidc_sub='duplicate-subject',
            confirmed=True,
        )
        db.session.add(existing_user)
        db.session.commit()

        with self.client.session_transaction() as client_session:
            client_session[OIDC_PENDING_PROFILE_SESSION_KEY] = {
                'sub': 'duplicate-subject',
                'issued_at': int(time.time()),
            }

        response = self.client.post('/auth/eduid/create-profile')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.query.filter_by(oidc_sub='duplicate-subject').count(), 1)
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(existing_user.id))


if __name__ == '__main__':
    unittest.main()
