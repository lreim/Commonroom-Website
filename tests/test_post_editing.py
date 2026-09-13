import unittest

from app import create_app, db
from app.models import Post, Role, User


class PostEditingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        self.client = self.app.test_client()
        user_role = Role.query.filter_by(name='User').one()
        self.owner = User(
            email='owner@ethz.ch',
            username='post-owner',
            password='OwnerPassword1',
            confirmed=True,
            role=user_role,
        )
        self.other_user = User(
            email='other@ethz.ch',
            username='other-user',
            password='OtherPassword1',
            confirmed=True,
            role=user_role,
        )
        db.session.add_all([self.owner, self.other_user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        response = self.client.post(
            '/auth/login',
            data={'email': email, 'password': password},
        )
        self.assertEqual(response.status_code, 302)

    def test_author_can_edit_post_and_feed_marks_it_as_edited(self):
        post = Post(
            body='Original text',
            author=self.owner,
            post_type='relate',
        )
        db.session.add(post)
        db.session.commit()
        original_timestamp = post.timestamp
        self._login('owner@ethz.ch', 'OwnerPassword1')

        response = self.client.post(
            f'/post/{post.id}/edit',
            data={'body': 'Updated text', 'next': '/post'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/post'))
        updated_post = db.session.get(Post, post.id)
        self.assertEqual(updated_post.body, 'Updated text')
        self.assertIsNotNone(updated_post.edited_at)
        self.assertEqual(updated_post.timestamp, original_timestamp)

        feed_response = self.client.get('/post')
        self.assertIn(b'Updated text', feed_response.data)
        self.assertIn(b'post-edited-label', feed_response.data)
        self.assertIn(b'edited', feed_response.data)

    def test_other_user_cannot_edit_post(self):
        post = Post(
            body='Owner-only text',
            author=self.owner,
            post_type='question',
        )
        db.session.add(post)
        db.session.commit()
        self._login('other@ethz.ch', 'OtherPassword1')

        response = self.client.post(
            f'/post/{post.id}/edit',
            data={'body': 'Unauthorized change'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(db.session.get(Post, post.id).body, 'Owner-only text')

    def test_starter_post_uses_separate_admin_editor(self):
        starter_post = Post(
            body='Platform starter',
            author_id=None,
            post_type='question',
            is_starter=True,
        )
        db.session.add(starter_post)
        db.session.commit()
        self._login('owner@ethz.ch', 'OwnerPassword1')

        response = self.client.get(f'/post/{starter_post.id}/edit')

        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
