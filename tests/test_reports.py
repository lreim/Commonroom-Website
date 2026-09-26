import unittest
from unittest.mock import patch

from sqlalchemy import text

from app import create_app, db
from app.models import ContentReport, Conversation, Message, Post, Role, User


class ContentReportsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config.update(WTF_CSRF_ENABLED=False, TALKTO_SITE_ORIGIN='https://commonroom.ch')
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        Role.insert_roles()
        role = Role.query.filter_by(name='User').one()
        admin_role = Role.query.filter_by(name='Administrator').one()
        self.users = [User(email=f'{name}@ethz.ch', username=name, password='Password123', confirmed=True,
                           role=admin_role if name == 'admin' else role)
                      for name in ['author', 'reporter', 'outsider', 'admin']]
        db.session.add_all(self.users)
        db.session.flush()
        self.author, self.reporter, self.outsider, self.admin = self.users
        self.post = Post(body='Original post', author=self.author)
        self.reply = Post(body='<script>reply</script>', author=self.author, parent=self.post)
        self.conversation = Conversation(user_a_id=self.author.id, user_b_id=self.reporter.id)
        db.session.add_all([self.post, self.reply, self.conversation])
        db.session.flush()
        self.message = Message(body='Private message', author_id=self.author.id, conversation_id=self.conversation.id)
        db.session.add(self.message)
        db.session.commit()
        self.client = self.app.test_client()
        self.mail_patch = patch('app.email.send_async_email')
        self.mail = self.mail_patch.start()

    def tearDown(self):
        self.mail_patch.stop()
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        self.client.post('/auth/logout')
        self.client.post('/auth/login', data={'email': user.email, 'password': 'Password123'})

    def report(self, kind='post', target=None):
        return self.client.post(f'/reports/{kind}/{target or self.reply.id}')

    def test_report_mail_snapshot_duplicate_and_counts(self):
        self.login(self.reporter)
        self.assertEqual(self.report().status_code, 201)
        report = ContentReport.query.one()
        self.assertEqual(report.reporter_id, self.reporter.id)
        self.assertEqual(report.author_id, self.author.id)
        self.assertIsNotNone(report.email_sent_at)
        payload = self.mail.call_args.args[1]
        self.assertEqual(payload['To'], 'report-abuse@commonroom.ch')
        for value in ['reporter', 'author', 'UTC', f'post #{self.reply.id}',
                      f'https://commonroom.ch/admin/reports/{report.id}#reported-content']:
            self.assertIn(value, payload['TextBody'])
        encrypted = db.session.execute(text('SELECT body FROM content_reports')).scalar()
        self.assertEqual(encrypted, '<script>reply</script>')
        self.assertEqual(self.report().status_code, 200)
        self.assertEqual(ContentReport.query.count(), 1)
        self.mail.assert_called_once()
        self.login(self.outsider)
        self.assertEqual(self.report().status_code, 201)
        self.login(self.admin)
        response = self.client.get('/admin/reports')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<strong>2</strong> reports', response.data)
        self.assertIn(b'<td>2</td>', response.data)
        detail = self.client.get(f'/admin/reports/{report.id}')
        self.assertIn(f'/post/{self.post.id}#post-{self.reply.id}'.encode(), detail.data)
        self.assertIn(b'&lt;script&gt;reply&lt;/script&gt;', detail.data)
        self.reply.body = 'Edited text'
        db.session.commit()
        self.assertIn(b'&lt;script&gt;reply&lt;/script&gt;', self.client.get(f'/admin/reports/{report.id}').data)
        db.session.delete(self.reply)
        db.session.commit()
        self.assertIn(b'original content has been deleted', self.client.get(f'/admin/reports/{report.id}').data)

    def test_chat_access_and_admin_isolation(self):
        self.login(self.outsider)
        self.assertEqual(self.report('message', self.message.id).status_code, 403)
        self.login(self.author)
        self.assertEqual(self.report('message', self.message.id).status_code, 403)
        self.login(self.reporter)
        self.assertEqual(self.report('message', self.message.id).status_code, 201)
        report_id = ContentReport.query.one().id
        for path in ['/admin/reports', f'/admin/reports/{report_id}']:
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post(f'/admin/reports/{report_id}/resend').status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(f'/chat/{self.conversation.id}').status_code, 403)
        response = self.client.get(f'/admin/reports/{report_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Private message', response.data)

    def test_failed_delivery_is_saved_and_admin_can_retry(self):
        self.login(self.reporter)
        self.mail.side_effect = RuntimeError('Mail unavailable')
        with self.assertLogs(self.app.logger, level='ERROR'):
            self.assertEqual(self.report().status_code, 201)
        report = ContentReport.query.one()
        self.assertIsNone(report.email_sent_at)
        self.login(self.admin)
        self.assertIn(b'1 report emails have not been sent', self.client.get('/admin/reports').data)
        self.mail.side_effect = None
        self.assertEqual(self.client.post(f'/admin/reports/{report.id}/resend').status_code, 302)
        self.assertIsNotNone(report.email_sent_at)
        calls = self.mail.call_count
        self.client.post(f'/admin/reports/{report.id}/resend')
        self.assertEqual(self.mail.call_count, calls)

    def test_authentication_csrf_invalid_targets_and_starter_posts(self):
        self.assertEqual(self.report().status_code, 302)
        self.assertEqual(self.client.get('/admin/reports').status_code, 302)
        self.login(self.reporter)
        self.assertEqual(self.report('invalid', self.reply.id).status_code, 404)
        self.assertEqual(self.report('post', 99999).status_code, 404)
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.report().status_code, 400)
        self.app.config['WTF_CSRF_ENABLED'] = False
        starter = Post(body='Starter', is_starter=True)
        db.session.add(starter)
        db.session.commit()
        self.assertEqual(self.report('post', starter.id).status_code, 201)
        self.assertEqual(ContentReport.query.one().author_username, 'CommonRoom Admin')

    def test_buttons_on_posts_profiles_and_incoming_chat_only(self):
        self.login(self.reporter)
        for path in ['/post', f'/post/{self.post.id}', f'/user/{self.author.username}']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'data-report-url="/reports/post/', response.data)
        own = Message(body='My own message', author_id=self.reporter.id, conversation_id=self.conversation.id)
        db.session.add(own)
        db.session.commit()
        response = self.client.get(f'/chat/{self.conversation.id}')
        self.assertIn(f'data-report-url="/reports/message/{self.message.id}"'.encode(), response.data)
        self.assertNotIn(f'data-report-url="/reports/message/{own.id}"'.encode(), response.data)
        self.assertIn(b'Report this message directly.', response.data)
        self.assertNotIn(b'href="/admin/reports"', response.data)
        self.login(self.admin)
        self.assertIn(b'href="/admin/reports"', self.client.get('/post').data)
