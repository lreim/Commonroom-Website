import unittest

from app import create_app, db
from app.models import Role, Tag, User


class TagSearchTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app.config.update(WTF_CSRF_ENABLED=False, AUTH_MODE="legacy")
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        Tag.seed_defaults()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, email, username):
        user = User(
            email=email,
            username=username,
            password="Password123",
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def test_one_matching_tag_is_enough_when_five_tags_are_selected(self):
        viewer = self._create_user("viewer@ethz.ch", "search-viewer")
        matching_user = self._create_user("match@ethz.ch", "one-tag-match")
        matching_user.tags.append(Tag.query.filter_by(name="burnout").one())
        db.session.commit()

        response = self.client.post(
            "/auth/login",
            data={"email": viewer.email, "password": "Password123"},
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(
            "/tags/search",
            query_string=[
                ("tags", "sleep"),
                ("tags", "stress"),
                ("tags", "motivation"),
                ("tags", "burnout"),
                ("tags", "loneliness"),
            ],
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        matching_profiles = {
            user["username"]
            for match in payload["matches"]
            for user in match["users"]
        }
        self.assertIn("one-tag-match", matching_profiles)


if __name__ == "__main__":
    unittest.main()
