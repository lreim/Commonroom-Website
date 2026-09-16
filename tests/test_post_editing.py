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

    def test_admin_mode_reply_belongs_to_personal_profile_and_is_editable(self):
        administrator_role = Role.query.filter_by(name='Administrator').one()
        administrator = User(
            email='admin@ethz.ch',
            username='admin-personal-profile',
            password='AdminPassword1',
            confirmed=True,
            role=administrator_role,
        )
        root_post = Post(
            body='A post that receives an Admin reply',
            author=self.other_user,
            post_type='question',
        )
        db.session.add_all([administrator, root_post])
        db.session.commit()
        self._login('admin@ethz.ch', 'AdminPassword1')

        response = self.client.post(
            '/post',
            data={
                'body': 'My editable reply',
                'reply_to_id': root_post.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        reply = Post.query.filter_by(body='My editable reply').one()
        self.assertEqual(reply.author_id, administrator.id)
        self.assertFalse(reply.is_starter)

        thread_response = self.client.get(f'/post/{root_post.id}')
        self.assertIn(
            f'/post/{reply.id}/edit'.encode(),
            thread_response.data,
        )

        edit_response = self.client.post(
            f'/post/{reply.id}/edit',
            data={'body': 'My updated reply'},
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(db.session.get(Post, reply.id).body, 'My updated reply')

    def test_administrator_can_edit_an_existing_ownerless_starter_reply(self):
        administrator_role = Role.query.filter_by(name='Administrator').one()
        administrator = User(
            email='admin@ethz.ch',
            username='admin-personal-profile',
            password='AdminPassword1',
            confirmed=True,
            role=administrator_role,
        )
        root_post = Post(
            body='Root starter post',
            author_id=None,
            post_type='question',
            is_starter=True,
        )
        old_reply = Post(
            body='Old ownerless Admin reply',
            author_id=None,
            parent=root_post,
            post_type='question',
            is_starter=True,
        )
        db.session.add_all([administrator, root_post, old_reply])
        db.session.commit()
        self._login('admin@ethz.ch', 'AdminPassword1')

        response = self.client.post(
            f'/post/{old_reply.id}/edit',
            data={'body': 'Corrected Admin reply'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(Post, old_reply.id).body, 'Corrected Admin reply')

    def test_reply_count_opens_complete_thread_while_reply_button_stays_inline(self):
        post = Post(
            body='Root post with replies',
            author=self.owner,
            post_type='question',
        )
        reply = Post(
            body='An existing reply',
            author=self.other_user,
            parent=post,
            post_type='question',
        )
        nested_reply = Post(
            body='A nested reply',
            author=self.owner,
            parent=reply,
            post_type='question',
        )
        db.session.add_all([post, reply, nested_reply])
        db.session.commit()
        self._login('owner@ethz.ch', 'OwnerPassword1')

        feed_response = self.client.get('/post')
        thread_target = f'/post/{post.id}'
        self.assertIn(f'href="{thread_target}"'.encode(), feed_response.data)
        self.assertIn(b'2 replies', feed_response.data)
        self.assertIn(
            f'data-reply-toggle id="reply-{post.id}"'.encode(),
            feed_response.data,
        )

        thread_response = self.client.get(thread_target)
        self.assertEqual(thread_response.status_code, 200)
        self.assertIn(b'class="post-thread-branch" data-thread-toggle open', thread_response.data)
        self.assertIn(b'An existing reply', thread_response.data)
        self.assertIn(b'A nested reply', thread_response.data)
        self.assertIn(b'post-thread-reply-context', thread_response.data)
        self.assertIn(b'Replying to', thread_response.data)
        self.assertNotIn(b'style="margin-left: 48px;"', thread_response.data)

    def test_reply_can_be_related(self):
        root = Post(body='Root', author=self.owner, post_type='question')
        reply = Post(
            body='Relatable reply',
            author=self.other_user,
            parent=root,
            post_type='question',
        )
        db.session.add_all([root, reply])
        db.session.commit()
        self._login('owner@ethz.ch', 'OwnerPassword1')

        response = self.client.post(f'/post/{reply.id}/like')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['liked'])
        self.assertEqual(response.get_json()['count'], 1)
        thread_response = self.client.get(f'/post/{root.id}')
        self.assertIn(f'data-like-url="/post/{reply.id}/like"'.encode(), thread_response.data)


if __name__ == '__main__':
    unittest.main()
