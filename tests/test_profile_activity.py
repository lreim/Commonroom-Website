import unittest
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import Post, Role, User


class ProfileActivityTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        role = Role.query.filter_by(name='User').one()
        self.profile_user = User(
            email='profile@ethz.ch',
            username='profile-user',
            password='ProfilePassword1',
            confirmed=True,
            role=role,
        )
        self.other_user = User(
            email='other@ethz.ch',
            username='other-user',
            password='OtherPassword1',
            confirmed=True,
            role=role,
        )
        db.session.add_all([self.profile_user, self.other_user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_profile_activity_separates_posts_and_replies_with_context(self):
        now = datetime.now(timezone.utc)
        own_post = Post(
            body='A recent profile post',
            author=self.profile_user,
            post_type='question',
            timestamp=now - timedelta(days=1),
        )
        other_root = Post(
            body='The original conversation topic',
            author=self.other_user,
            post_type='relate',
            timestamp=now - timedelta(days=12),
        )
        own_reply = Post(
            body='A reply from this profile',
            author=self.profile_user,
            parent=other_root,
            post_type='relate',
            timestamp=now - timedelta(days=10),
        )
        db.session.add_all([own_post, other_root, own_reply])
        db.session.commit()

        response = self.app.test_client().get(
            '/user/profile-user?activity=replies&sort=oldest'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Activity', response.data)
        self.assertIn(b'1 entry', response.data)
        self.assertIn(b'1 post', response.data)
        self.assertIn(b'1 reply', response.data)
        self.assertIn(b'A reply from this profile', response.data)
        self.assertIn(b'Replying to', response.data)
        self.assertIn(b'The original conversation topic', response.data)
        self.assertNotIn(b'A recent profile post</a>', response.data)
        self.assertIn(f'/post/{other_root.id}#post-{own_reply.id}'.encode(), response.data)

    def test_oldest_sort_places_earlier_group_before_this_week(self):
        now = datetime.now(timezone.utc)
        recent_post = Post(
            body='Recent activity',
            author=self.profile_user,
            post_type='question',
            timestamp=now - timedelta(days=1),
        )
        older_post = Post(
            body='Older activity',
            author=self.profile_user,
            post_type='relate',
            timestamp=now - timedelta(days=10),
        )
        db.session.add_all([recent_post, older_post])
        db.session.commit()

        response = self.app.test_client().get(
            '/user/profile-user?activity=all&sort=oldest'
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertLess(html.index('Earlier'), html.index('This week'))
        self.assertLess(html.index('Older activity'), html.index('Recent activity'))


if __name__ == '__main__':
    unittest.main()
