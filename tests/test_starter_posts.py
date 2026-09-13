import unittest

from app import create_app, db
from app.models import Post, Role, User


class StarterPostAdminTestCase(unittest.TestCase):
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

    def _create_user(self, email, username, password, role=None):
        user = User(
            email=email,
            username=username,
            password=password,
            confirmed=True,
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def _login(self, email, password):
        response = self.client.post(
            '/auth/login',
            data={'email': email, 'password': password},
        )
        self.assertEqual(response.status_code, 302)

    def test_admin_can_write_and_edit_starter_post(self):
        admin = self._create_user(
            self.app.config['TALKTO_ADMIN'],
            'commonroom-admin',
            'AdminPassword1',
        )
        self.assertTrue(admin.is_administrator())
        self._login(self.app.config['TALKTO_ADMIN'], 'AdminPassword1')

        create_response = self.client.post(
            '/admin/starter-posts',
            data={
                'body': 'What helped you settle into university life?',
                'post_type': 'question',
            },
        )

        self.assertEqual(create_response.status_code, 302)
        starter_post = Post.query.one()
        self.assertTrue(starter_post.is_starter)
        self.assertIsNone(starter_post.author_id)
        self.assertEqual(starter_post.post_type, 'question')

        edit_response = self.client.post(
            f'/admin/starter-posts/{starter_post.id}/edit',
            data={
                'body': 'What helped you feel at home at university?',
                'post_type': 'relate',
            },
        )

        self.assertEqual(edit_response.status_code, 302)
        updated_post = db.session.get(Post, starter_post.id)
        self.assertEqual(updated_post.body, 'What helped you feel at home at university?')
        self.assertEqual(updated_post.post_type, 'relate')
        self.assertTrue(updated_post.is_starter)

    def test_ordinary_user_cannot_open_starter_post_admin(self):
        ordinary_role = Role.query.filter_by(name='User').one()
        self._create_user(
            'ordinary@ethz.ch',
            'ordinary-user',
            'UserPassword1',
            role=ordinary_role,
        )
        self._login('ordinary@ethz.ch', 'UserPassword1')

        response = self.client.get('/admin/starter-posts')

        self.assertEqual(response.status_code, 403)

    def test_regular_post_cannot_be_edited_as_starter_post(self):
        admin = self._create_user(
            self.app.config['TALKTO_ADMIN'],
            'commonroom-admin',
            'AdminPassword1',
        )
        regular_post = Post(
            body='A regular community post',
            author=admin,
            post_type='relate',
            is_starter=False,
        )
        db.session.add(regular_post)
        db.session.commit()
        self._login(self.app.config['TALKTO_ADMIN'], 'AdminPassword1')

        response = self.client.get(f'/admin/starter-posts/{regular_post.id}/edit')

        self.assertEqual(response.status_code, 404)

    def test_starter_post_is_public_platform_content_without_admin_profile(self):
        admin = self._create_user(
            self.app.config['TALKTO_ADMIN'],
            'commonroom-admin',
            'AdminPassword1',
        )
        starter_post = Post(
            body='A conversation starter from CommonRoom',
            author=admin,
            post_type='question',
            is_starter=True,
        )
        db.session.add(starter_post)
        db.session.commit()

        feed_response = self.client.get('/post')

        self.assertEqual(feed_response.status_code, 200)
        self.assertIn(b'Starter post', feed_response.data)
        self.assertIn(b'A conversation starter from CommonRoom', feed_response.data)
        self.assertIn(b'Logo_Website_small.jpg', feed_response.data)
        self.assertIn(b'/admin/profile', feed_response.data)
        self.assertNotIn(b'commonroom-admin', feed_response.data)

        admin_profile_response = self.client.get('/admin/profile')

        self.assertEqual(admin_profile_response.status_code, 200)
        self.assertIn(b'<h1>Admin</h1>', admin_profile_response.data)
        self.assertIn(b'data-open-contact-panel', admin_profile_response.data)
        self.assertIn(b'A conversation starter from CommonRoom', admin_profile_response.data)
        self.assertNotIn(b'commonroom-admin', admin_profile_response.data)

        profile_response = self.client.get('/user/commonroom-admin')

        self.assertEqual(profile_response.status_code, 200)
        self.assertNotIn(b'A conversation starter from CommonRoom', profile_response.data)

        ordinary_role = Role.query.filter_by(name='User').one()
        self._create_user(
            'ordinary@ethz.ch',
            'ordinary-user',
            'UserPassword1',
            role=ordinary_role,
        )
        self._login('ordinary@ethz.ch', 'UserPassword1')

        thread_response = self.client.get(f'/post/{starter_post.id}')

        self.assertEqual(thread_response.status_code, 200)
        self.assertIn(b'Starter post', thread_response.data)
        self.assertNotIn(b'commonroom-admin', thread_response.data)


if __name__ == '__main__':
    unittest.main()
