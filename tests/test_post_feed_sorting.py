import unittest
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import Post, Role, User


class PostFeedSortingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        self.client = self.app.test_client()

        user = User(
            email='feed-sort@ethz.ch',
            username='feed-sort-user',
            password='Password123',
            confirmed=True,
            role=Role.query.filter_by(name='User').one(),
        )
        now = datetime.now(timezone.utc)
        older_root = Post(
            body='Older root with fresh nested reply',
            author=user,
            timestamp=now - timedelta(days=3),
            post_type='question',
        )
        direct_reply = Post(
            body='An older direct reply',
            author=user,
            parent=older_root,
            timestamp=now - timedelta(days=2),
            post_type='question',
        )
        newer_root = Post(
            body='Newer root without replies',
            author=user,
            timestamp=now - timedelta(hours=2),
            post_type='relate',
        )
        nested_reply = Post(
            body='The latest nested reply',
            author=user,
            parent=direct_reply,
            timestamp=now - timedelta(minutes=10),
            post_type='question',
        )
        db.session.add_all([user, older_root, direct_reply, newer_root, nested_reply])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_latest_activity_is_default_and_includes_nested_replies(self):
        response = self.client.get('/post')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            html.index('Older root with fresh nested reply'),
            html.index('Newer root without replies'),
        )
        self.assertIn('value="latest_activity" selected', html)

    def test_newest_posts_ignores_reply_activity(self):
        response = self.client.get('/post?sort=most_recent')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            html.index('Newer root without replies'),
            html.index('Older root with fresh nested reply'),
        )

    def test_unanswered_view_only_shows_posts_without_replies(self):
        response = self.client.get('/post?sort=unanswered')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Newer root without replies', response.data)
        self.assertNotIn(b'Older root with fresh nested reply', response.data)
        self.assertIn(b'value="unanswered" selected', response.data)

    def test_still_thinking_view_only_shows_matching_status(self):
        still_thinking = Post.query.filter_by(body='Newer root without replies').one()
        still_thinking.thread_status = 'still_thinking'
        db.session.commit()

        response = self.client.get('/post?sort=still_thinking')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Newer root without replies', response.data)
        self.assertNotIn(b'Older root with fresh nested reply', response.data)
        self.assertIn(b'value="still_thinking" selected', response.data)
        self.assertIn(b'Still thinking about this', response.data)

    def test_confession_can_be_created_and_filtered(self):
        self.client.post(
            '/auth/login',
            data={'email': 'feed-sort@ethz.ch', 'password': 'Password123'},
        )
        response = self.client.post(
            '/post',
            data={'body': 'A new confession', 'post_type': 'confession'},
        )

        self.assertEqual(response.status_code, 302)
        confession = Post.query.filter_by(body='A new confession').one()
        self.assertEqual(confession.post_type, 'confession')

        filtered = self.client.get('/post?type=confession')
        self.assertIn(b'A new confession', filtered.data)
        self.assertNotIn(b'Newer root without replies', filtered.data)
        self.assertIn(b'>Confession</span>', filtered.data)


if __name__ == '__main__':
    unittest.main()
