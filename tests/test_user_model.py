import unittest
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import User, Role, AnonymousUser, Permission


class UserModelTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        # Dein User.__init__ erwartet diesen Config-Key:
        self.app.config["TALKTO_ADMIN"] = "admin@example.com"

        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_password_setter(self):
        u = User(password="cat")
        self.assertIsNotNone(u.password_hash)

    def test_no_password_getter(self):
        u = User(password="cat")
        with self.assertRaises(AttributeError):
            _ = u.password

    def test_password_verification(self):
        u = User(password="cat")
        self.assertTrue(u.verify_password("cat"))
        self.assertFalse(u.verify_password("dog"))

    def test_password_salts_are_random(self):
        u = User(password="cat")
        u2 = User(password="cat")
        self.assertNotEqual(u.password_hash, u2.password_hash)

    def test_roles_and_permissions(self):
        Role.insert_roles()
        u = User(email="john@example.com", password="cat")
        self.assertTrue(u.can(Permission.WRITE_ARTICLES))
        self.assertFalse(u.can(Permission.MODERATE_COMMENTS))

    def test_anonymous_user(self):
        u = AnonymousUser()
        self.assertFalse(u.can(Permission.FOLLOW))

    def test_login_throttling_fields_persist_on_user(self):
        user = User(email="persist@example.com", password="cat")
        db.session.add(user)
        db.session.commit()

        locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        user.failed_login_attempts = 4
        user.login_locked_until = locked_until
        user.login_lockout_count = 2
        user.login_lockout_window_started_at = datetime.now(timezone.utc)
        user.account_locked_until = datetime.now(timezone.utc) + timedelta(hours=24)
        db.session.add(user)
        db.session.commit()

        loaded = User.query.get(user.id)
        self.assertEqual(loaded.failed_login_attempts, 4)
        self.assertIsNotNone(loaded.login_locked_until)
        self.assertEqual(loaded.login_lockout_count, 2)
        self.assertIsNotNone(loaded.login_lockout_window_started_at)
        self.assertIsNotNone(loaded.account_locked_until)


if __name__ == "__main__":
    unittest.main()



# WICHTIG: 
# User.password('cat') ist falsch (auch wenn password() eine normale Methode wäre),
# da password eine Instanz erwartet, also ein u = User()
# dann ginge User.password(u, 'cat'), oder besser erst u definieren.
