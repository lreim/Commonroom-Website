import time
import unittest
from unittest.mock import patch

from authlib.integrations.base_client.errors import OAuthError
from flask import redirect, session

from app import create_app, db
from app.auth.views import OIDC_PENDING_PROFILE_SESSION_KEY
from app.models import Post, Role, User


class FakeEduIDClient:
    def __init__(self, token=None, callback_error=None, userinfo=None):
        self.token = token
        self.callback_error = callback_error
        self.userinfo_claims = userinfo
        self.redirect_kwargs = None
        self.framework = FakeStateFramework()

    def authorize_redirect(self, **kwargs):
        self.redirect_kwargs = kwargs
        self.framework.set_state_data(
            session,
            'fake-state',
            {
                'redirect_uri': kwargs.get('redirect_uri'),
                'nonce': kwargs.get('nonce'),
            },
        )
        return redirect('https://login.eduid.ch/authorize?state=fake-state')

    def authorize_access_token(self):
        if self.callback_error:
            raise self.callback_error
        return self.token

    def userinfo(self, token):
        if self.userinfo_claims is not None:
            return self.userinfo_claims
        return token['userinfo']


class FakeStateFramework:
    @staticmethod
    def _key(state):
        return f'_state_eduid_{state}'

    def get_state_data(self, client_session, state):
        stored = client_session.get(self._key(state))
        return stored.get('data') if isinstance(stored, dict) else None

    def set_state_data(self, client_session, state, data):
        client_session[self._key(state)] = {'data': data}


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
        self.assertEqual(self.client.get('/auth/eduid/link-account').status_code, 404)

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

    def test_legacy_login_returns_to_requested_local_page(self):
        user = User(
            email='student@ethz.ch',
            username='legacy-user',
            password='LegacyPassword1',
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()

        response = self.client.post(
            '/auth/login?next=/rules',
            data={
                'email': 'student@ethz.ch',
                'password': 'LegacyPassword1',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/rules'))

    def test_navbar_login_keeps_the_current_page_as_destination(self):
        response = self.client.get('/rules')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/auth/login?next=/rules', response.data)

    def test_existing_oidc_user_returns_to_requested_page(self):
        self._enable_oidc()
        user = User(
            username='existing-user',
            oidc_sub='existing-subject',
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        fake_client = FakeEduIDClient(token=self._student_token('existing-subject'))

        with patch('app.auth.views._get_eduid_client', return_value=FakeEduIDClient()):
            login_response = self.client.get('/auth/login?next=/rules')
        self.assertEqual(login_response.status_code, 302)
        with self.client.session_transaction() as client_session:
            client_session.pop('oidc_next_url', None)

        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            callback_response = self.client.get('/auth/eduid/callback?state=fake-state')

        self.assertEqual(callback_response.status_code, 302)
        self.assertTrue(callback_response.location.endswith('/rules'))

    def test_oidc_mode_uses_oidc_for_normal_login(self):
        self.app.config['AUTH_MODE'] = 'oidc'
        fake_client = FakeEduIDClient()
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/login')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://login.eduid.ch/authorize?state=fake-state')
        self.assertEqual(self.client.get('/auth/legacy/login').status_code, 404)
        self.assertEqual(
            fake_client.redirect_kwargs['redirect_uri'],
            'https://commonroom.ch/auth/eduid/callback',
        )
        self.assertTrue(fake_client.redirect_kwargs['nonce'])

    def test_oidc_mode_never_displays_legacy_registration(self):
        self._enable_oidc()
        fake_client = FakeEduIDClient()
        with patch('app.auth.views._get_eduid_client', return_value=fake_client):
            response = self.client.get('/auth/register?next=/post')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://login.eduid.ch/authorize?state=fake-state')
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('oidc_next_url'), '/post')

    def test_anonymous_post_actions_use_central_login(self):
        post = Post(body='A public question', post_type='question', is_starter=True)
        db.session.add(post)
        db.session.commit()

        response = self.client.get('/post')

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data.count(b'/auth/login?next='), 2)
        self.assertNotIn(b'/auth/register?next=', response.data)

        self._enable_oidc()
        post_response = self.client.post(
            '/post',
            data={'body': 'Anonymous submission', 'post_type': 'question'},
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertIn('/auth/login?next=', post_response.location)

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
        self.assertIsNone(user.contact_email)
        self.assertIsNone(user.password_hash)
        self.assertTrue(user.confirmed)
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(user.id))
            self.assertNotIn(OIDC_PENDING_PROFILE_SESSION_KEY, client_session)

        response = self.client.get('/auth/eduid/welcome')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to CommonRoom', response.data)
        self.assertIn(user.username.encode(), response.data)

    def test_unknown_oidc_user_can_link_existing_legacy_profile(self):
        self._enable_oidc()
        existing_user = User(
            email='existing@ethz.ch',
            username='existing-profile',
            password='ExistingPassword1',
            confirmed=True,
            about_me='Keep this profile data.',
        )
        db.session.add(existing_user)
        db.session.commit()

        with patch(
            'app.auth.views._get_eduid_client',
            return_value=FakeEduIDClient(token=self._student_token('new-linked-subject')),
        ):
            callback_response = self.client.get('/auth/eduid/callback')

        self.assertTrue(callback_response.location.endswith('/auth/eduid/create-profile'))
        profile_response = self.client.get('/auth/eduid/create-profile')
        self.assertIn(b'Connect my existing profile', profile_response.data)

        link_response = self.client.post(
            '/auth/eduid/link-account',
            data={
                'email': 'existing@student.ethz.ch',
                'password': 'ExistingPassword1',
            },
        )

        self.assertEqual(link_response.status_code, 302)
        self.assertEqual(User.query.count(), 1)
        linked_user = db.session.get(User, existing_user.id)
        self.assertEqual(linked_user.oidc_sub, 'new-linked-subject')
        self.assertEqual(linked_user.about_me, 'Keep this profile data.')
        with self.client.session_transaction() as client_session:
            self.assertEqual(client_session.get('_user_id'), str(existing_user.id))
            self.assertNotIn(OIDC_PENDING_PROFILE_SESSION_KEY, client_session)

    def test_oidc_link_rejects_wrong_legacy_password(self):
        self._enable_oidc()
        existing_user = User(
            email='existing@ethz.ch',
            username='existing-profile',
            password='ExistingPassword1',
            confirmed=True,
        )
        db.session.add(existing_user)
        db.session.commit()
        with self.client.session_transaction() as client_session:
            client_session[OIDC_PENDING_PROFILE_SESSION_KEY] = {
                'sub': 'pending-subject',
                'issued_at': int(time.time()),
            }

        response = self.client.post(
            '/auth/eduid/link-account',
            data={
                'email': 'existing@ethz.ch',
                'password': 'WrongPassword1',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(db.session.get(User, existing_user.id).oidc_sub)
        self.assertEqual(db.session.get(User, existing_user.id).failed_login_attempts, 1)
        with self.client.session_transaction() as client_session:
            self.assertNotIn('_user_id', client_session)
            self.assertEqual(
                client_session[OIDC_PENDING_PROFILE_SESSION_KEY]['sub'],
                'pending-subject',
            )

    def test_oidc_link_does_not_replace_another_subject(self):
        self._enable_oidc()
        existing_user = User(
            email='linked@ethz.ch',
            username='linked-profile',
            password='ExistingPassword1',
            oidc_sub='original-subject',
            confirmed=True,
        )
        db.session.add(existing_user)
        db.session.commit()
        with self.client.session_transaction() as client_session:
            client_session[OIDC_PENDING_PROFILE_SESSION_KEY] = {
                'sub': 'different-subject',
                'issued_at': int(time.time()),
            }

        response = self.client.post(
            '/auth/eduid/link-account',
            data={
                'email': 'linked@ethz.ch',
                'password': 'ExistingPassword1',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(User, existing_user.id).oidc_sub, 'original-subject')
        with self.client.session_transaction() as client_session:
            self.assertNotIn('_user_id', client_session)

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

    def test_oauth_error_logs_only_sanitized_error_code(self):
        self._enable_oidc()
        sensitive_description = 'secret token and authorization code'
        fake_client = FakeEduIDClient(
            callback_error=OAuthError(
                error='invalid_client',
                description=sensitive_description,
            )
        )

        with self.assertLogs(self.app.logger, level='WARNING') as captured_logs:
            with patch('app.auth.views._get_eduid_client', return_value=fake_client):
                response = self.client.get('/auth/eduid/callback')

        log_output = '\n'.join(captured_logs.output)
        self.assertEqual(response.status_code, 400)
        self.assertIn('oauth_error=invalid_client', log_output)
        self.assertNotIn(sensitive_description, log_output)

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
