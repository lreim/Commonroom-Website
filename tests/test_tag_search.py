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

    def test_guest_preview_returns_only_real_matching_profiles_and_keeps_full_search_private(self):
        matching_user = self._create_user("match@ethz.ch", "burnout-match")
        matching_user.tags.append(Tag.query.filter_by(name="burnout").one())
        self._create_user("other@ethz.ch", "unrelated-user")
        db.session.commit()

        response = self.client.get("/tags/preview", query_string={"tags": "burnout"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["profiles"],
            [{
                "username": "burnout-match",
                "avatar_url": matching_user.gravatar(size=56),
                "matching_tags": ["burnout"],
            }],
        )
        self.assertEqual(self.client.get("/tags/search").status_code, 302)

    def test_guest_preview_prioritizes_multiple_shared_tags_and_limits_profiles(self):
        both = self._create_user("both@ethz.ch", "both-tags")
        burnout = self._create_user("burnout@ethz.ch", "burnout-only")
        lonely = self._create_user("lonely@ethz.ch", "loneliness-only")
        burnout_tag = Tag.query.filter_by(name="burnout").one()
        loneliness_tag = Tag.query.filter_by(name="loneliness").one()
        both.tags.extend([burnout_tag, loneliness_tag])
        burnout.tags.append(burnout_tag)
        lonely.tags.append(loneliness_tag)
        db.session.commit()

        response = self.client.get(
            "/tags/preview",
            query_string=[("tags", "burnout"), ("tags", "loneliness")],
        )

        profiles = response.get_json()["profiles"]
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0]["username"], "both-tags")
        self.assertEqual(profiles[0]["matching_tags"], ["burnout", "loneliness"])
        self.assertTrue(all("email" not in profile for profile in profiles))


if __name__ == "__main__":
    unittest.main()
