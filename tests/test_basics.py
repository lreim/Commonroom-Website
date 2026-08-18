import unittest
from flask import current_app
from app import create_app, db

class BasicsTestCase(unittest.TestCase):
    def setUp(self):
        #creates a similar setup like app
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_app_exists(self):
        self.assertFalse(current_app is None)

    def test_app_is_testing(self):
        self.assertTrue(current_app.config['TESTING'])

    def test_default_admin_email_is_configured(self):
        self.assertEqual(current_app.config['TALKTO_ADMIN'], 'contact@commonroom.ch')

    def test_testing_secret_key_is_not_public_fallback(self):
        self.assertEqual(current_app.config['SECRET_KEY'], 'testing-secret-key')
