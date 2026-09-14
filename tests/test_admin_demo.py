import unittest

from app import create_app, db
from app.admin_demo import ADMIN_DEMO_SESSION_KEY
from app.models import Post, Role, User


class AdminDemoModeTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(
            WTF_CSRF_ENABLED=False,
            TALKTO_ADMIN='admin@ethz.ch',
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

    def _create_user(self, email, username, password, **kwargs):
        user = User(
            email=email,
            username=username,
            password=password,
            confirmed=True,
            **kwargs,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def test_admin_login_starts_in_switchable_demo_profile(self):
        admin = self._create_user(
            self.app.config['TALKTO_ADMIN'],
            'personal-admin-name',
            'AdminPassword1',
            about_me='My personal profile text.',
        )

        login_response = self.client.post(
            '/auth/login',
            data={'email': admin.email, 'password': 'AdminPassword1'},
        )

        self.assertEqual(login_response.status_code, 302)
        self.assertTrue(login_response.location.endswith('/'))
        with self.client.session_transaction() as client_session:
            self.assertIs(client_session.get(ADMIN_DEMO_SESSION_KEY), True)

        demo_response = self.client.get('/admin/profile')
        self.assertIn(b'<h1>Admin</h1>', demo_response.data)
        self.assertIn(b'COMMONROOM ADMIN', demo_response.data)
        self.assertIn(b'Show my personal profile', demo_response.data)
        self.assertNotIn(b'My personal profile text.', demo_response.data)

        direct_personal_response = self.client.get('/user/personal-admin-name')
        self.assertEqual(direct_personal_response.status_code, 200)
        self.assertIn(b'<h1>personal-admin-name</h1>', direct_personal_response.data)
        self.assertIn(b'My personal profile text.', direct_personal_response.data)
        self.assertNotIn(b'COMMONROOM ADMIN', direct_personal_response.data)

        switch_response = self.client.post('/admin/demo-profile/personal')

        self.assertEqual(switch_response.status_code, 302)
        with self.client.session_transaction() as client_session:
            self.assertIs(client_session.get(ADMIN_DEMO_SESSION_KEY), False)

        personal_response = self.client.get(switch_response.location)
        self.assertIn(b'<h1>personal-admin-name</h1>', personal_response.data)
        self.assertIn(b'My personal profile text.', personal_response.data)
        self.assertIn(b'Show Admin profile', personal_response.data)
        self.assertNotIn(b'>Starter Posts</a>', personal_response.data)

        personal_post_page = self.client.get('/post')
        self.assertIn(b'as personal-admin-name', personal_post_page.data)

        demo_switch_response = self.client.post('/admin/demo-profile/admin')

        self.assertEqual(demo_switch_response.status_code, 302)
        self.assertTrue(demo_switch_response.location.endswith('/admin/profile'))

        admin_post_response = self.client.post(
            '/post',
            data={
                'body': 'A platform post written in Admin mode.',
                'post_type': 'question',
            },
        )
        self.assertEqual(admin_post_response.status_code, 302)
        admin_post = Post.query.filter_by(
            body='A platform post written in Admin mode.'
        ).one()
        self.assertTrue(admin_post.is_starter)
        self.assertIsNone(admin_post.author_id)

        regular_post = Post(
            body='This remains a personal anonymous post.',
            author=admin,
            post_type='relate',
            is_starter=False,
        )
        db.session.add(regular_post)
        db.session.commit()

        post_feed_response = self.client.get('/post')

        self.assertEqual(post_feed_response.status_code, 200)
        self.assertIn(b'as Admin', post_feed_response.data)
        self.assertIn(b'href="/user/personal-admin-name"', post_feed_response.data)
        self.assertIn(b'This remains a personal anonymous post.', post_feed_response.data)

    def test_regular_user_does_not_enter_admin_demo_mode(self):
        ordinary_role = Role.query.filter_by(name='User').one()
        user = self._create_user(
            'student@ethz.ch',
            'ordinary-user',
            'UserPassword1',
            role=ordinary_role,
        )

        response = self.client.post(
            '/auth/login',
            data={'email': user.email, 'password': 'UserPassword1'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/'))
        with self.client.session_transaction() as client_session:
            self.assertNotIn(ADMIN_DEMO_SESSION_KEY, client_session)

        profile_response = self.client.get(f'/user/{user.username}')
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn(b'No posts have been published yet.', profile_response.data)
        self.assertNotIn(b'No starter posts have been published yet.', profile_response.data)

    def test_public_admin_profile_survives_missing_configured_admin_account(self):
        ordinary_role = Role.query.filter_by(name='User').one()
        user = self._create_user(
            'student@ethz.ch',
            'ordinary-user',
            'UserPassword1',
            role=ordinary_role,
        )
        self.app.config['TALKTO_ADMIN'] = 'missing-admin@ethz.ch'
        self.client.post(
            '/auth/login',
            data={'email': user.email, 'password': 'UserPassword1'},
        )

        response = self.client.get('/admin/profile')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<h1>Admin</h1>', response.data)
        self.assertIn(b'COMMONROOM ADMIN', response.data)


if __name__ == '__main__':
    unittest.main()
