import unittest

from app import create_app, db
from app.models import Post, Role, User


class ReplyNotificationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        role = Role.query.filter_by(name='User').one()
        self.owner = User(
            email='owner@ethz.ch',
            username='post-owner',
            password='OwnerPassword1',
            confirmed=True,
            role=role,
        )
        self.participant = User(
            email='participant@ethz.ch',
            username='thread-participant',
            password='ParticipantPassword1',
            confirmed=True,
            role=role,
        )
        self.other = User(
            email='other@ethz.ch',
            username='new-replier',
            password='OtherPassword1',
            confirmed=True,
            role=role,
        )
        db.session.add_all([self.owner, self.participant, self.other])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, user, password):
        response = self.client.post(
            '/auth/login',
            data={'email': user.email, 'password': password},
        )
        self.assertEqual(response.status_code, 302)

    def test_post_author_receives_reply_notification(self):
        root = Post(body='My post', author=self.owner, post_type='question')
        reply = Post(
            body='A reply for the owner',
            author=self.other,
            parent=root,
            post_type='question',
        )
        db.session.add_all([root, reply])
        db.session.commit()
        self._login(self.owner, 'OwnerPassword1')

        response = self.client.get('/')

        self.assertIn(b'new-replier replied to your post', response.data)
        self.assertIn(f'/post/{root.id}#post-{reply.id}'.encode(), response.data)
        self.assertIn(b'notification-menu-trigger has-unseen', response.data)

    def test_thread_participant_receives_later_nested_reply_notification(self):
        root = Post(body='Someone else\'s post', author=self.owner, post_type='question')
        participant_reply = Post(
            body='I joined this conversation',
            author=self.participant,
            parent=root,
            post_type='question',
        )
        later_reply = Post(
            body='A later nested response',
            author=self.other,
            parent=participant_reply,
            post_type='question',
        )
        db.session.add_all([root, participant_reply, later_reply])
        db.session.commit()
        self._login(self.participant, 'ParticipantPassword1')

        response = self.client.get('/')

        self.assertIn(
            b'new-replier replied to a post you also replied to',
            response.data,
        )
        self.assertIn(f'/post/{root.id}#post-{later_reply.id}'.encode(), response.data)
        self.assertNotIn(b'I joined this conversation</span>', response.data)

    def test_user_does_not_receive_notification_for_own_reply(self):
        root = Post(body='My post', author=self.owner, post_type='question')
        own_reply = Post(
            body='My own reply',
            author=self.owner,
            parent=root,
            post_type='question',
        )
        db.session.add_all([root, own_reply])
        db.session.commit()
        self._login(self.owner, 'OwnerPassword1')

        response = self.client.get('/')

        self.assertNotIn(b'replied to your post', response.data)
        self.assertNotIn(b'notification-menu-trigger has-unseen', response.data)


if __name__ == '__main__':
    unittest.main()
