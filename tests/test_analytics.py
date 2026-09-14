import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import create_app, db
from app.main.views import _build_visit_timeline
from app.models import PageVisit, Post, Role, User


class AnalyticsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app.config.update(
            WTF_CSRF_ENABLED=False,
            TALKTO_ADMIN="admin@ethz.ch",
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        Role.insert_roles()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, email, username, contact_email=None):
        user = User(
            email=email,
            username=username,
            password="Password123",
            contact_email=contact_email,
            confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        return user

    def _add_visit(self, page_key, path, token, session_token, minute, tracking_version=2, **kwargs):
        started_at = datetime.now(timezone.utc) - timedelta(minutes=minute)
        visit = PageVisit(
            page_key=page_key,
            path=path,
            device_type="mobile",
            visit_token=token,
            session_token=session_token,
            tracking_version=tracking_version,
            started_at=started_at,
            ended_at=started_at + timedelta(seconds=30),
            duration_seconds=30,
            **kwargs,
        )
        db.session.add(visit)

    def test_tracking_accepts_home_and_tab_session_token(self):
        response = self.client.post(
            "/analytics/page-visit",
            json={
                "page_key": "index",
                "path": "/",
                "duration_ms": 2500,
                "visit_token": "home-visit-one",
                "session_token": "tab-session-one",
                "device_type": "mobile",
                "acquisition_source": "campus-newsletter",
                "acquisition_medium": "email",
                "acquisition_campaign": "welcome-week",
            },
        )

        self.assertEqual(response.status_code, 204)
        visit = PageVisit.query.one()
        self.assertEqual(visit.page_key, "index")
        self.assertEqual(visit.session_token, "tab-session-one")
        self.assertEqual(visit.tracking_version, 2)
        self.assertEqual(visit.acquisition_medium, "email")

    def test_invalid_session_token_is_not_stored(self):
        self.client.post(
            "/analytics/page-visit",
            json={
                "page_key": "about",
                "path": "/about",
                "duration_ms": 1000,
                "visit_token": "about-visit-one",
                "session_token": "not allowed!",
                "device_type": "desktop",
            },
        )

        self.assertIsNone(PageVisit.query.one().session_token)

    def test_reload_token_is_counted_only_once(self):
        payload = {
            "page_key": "about",
            "path": "/about",
            "duration_ms": 1000,
            "visit_token": "same-page-load-token",
            "session_token": "same-tab-session",
            "device_type": "desktop",
        }

        self.client.post("/analytics/page-visit", json=payload)
        self.client.post("/analytics/page-visit", json=payload)

        self.assertEqual(PageVisit.query.count(), 1)

    def test_admin_login_removes_public_visits_from_same_tab_session(self):
        admin = self._create_user("admin@ethz.ch", "admin-user")
        self._add_visit("index", "/", "admin-before-login", "admin-tab", 2)
        self._add_visit("about", "/about", "someone-else", "other-tab", 1)
        db.session.commit()

        self.client.post(
            "/auth/login",
            data={"email": admin.email, "password": "Password123"},
        )
        response = self.client.post(
            "/analytics/page-visit",
            json={"session_token": "admin-tab"},
        )

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(PageVisit.query.filter_by(visit_token="admin-before-login").first())
        self.assertIsNotNone(PageVisit.query.filter_by(visit_token="someone-else").first())

    def test_tracking_script_reuses_page_token_on_reload(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'commonroomAnalyticsPageView', response.data)
        self.assertIn(b'navigationEntry.type === "reload"', response.data)

    def test_dashboard_shows_content_profiles_hours_and_journeys(self):
        admin = self._create_user("admin@ethz.ch", "admin-user")
        first_user = self._create_user(
            "first@ethz.ch",
            "first-user",
            contact_email="private@example.org",
        )
        self._create_user("second@ethz.ch", "second-user")

        relate_post = Post(body="Relatable", author=first_user, post_type="relate")
        question_post = Post(body="Question", author=first_user, post_type="question")
        db.session.add_all([relate_post, question_post])
        db.session.flush()
        db.session.add(
            Post(
                body="A reply",
                author=first_user,
                parent=relate_post,
                post_type="relate",
            )
        )

        self._add_visit("post", "/post", "journey-post", "journey-one", 1)
        self._add_visit("onboarding", "/onboarding", "journey-onboarding", "journey-one", 2)
        self._add_visit("index", "/", "journey-home", "journey-one", 3)
        db.session.commit()

        login_response = self.client.post(
            "/auth/login",
            data={"email": admin.email, "password": "Password123"},
        )
        self.assertEqual(login_response.status_code, 302)

        response = self.client.get("/analytics?range=24h")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Relate posts", response.data)
        self.assertIn(b"Question posts", response.data)
        self.assertIn(b"Replied posts", response.data)
        self.assertIn(b"With email", response.data)
        self.assertIn(b"Without email", response.data)
        self.assertIn(b"At what time did people visit?", response.data)
        self.assertIn(b"Where do people go after Home?", response.data)
        self.assertIn(b"Home", response.data)
        self.assertIn(b"Onboarding", response.data)
        self.assertIn(b"Posts", response.data)

    def test_24_hour_timeline_uses_zurich_time_labels(self):
        timeline = _build_visit_timeline("24h")
        expected_hour = datetime.now(timezone.utc).astimezone(
            ZoneInfo("Europe/Zurich")
        ).strftime("%H:00")

        self.assertEqual(timeline["timezone"], "Europe/Zurich")
        self.assertEqual(timeline["points"][-1]["label"], expected_hour)

    def test_previous_analytics_stays_separate_from_new_analytics(self):
        admin = self._create_user("admin@ethz.ch", "admin-user")
        self._add_visit("about", "/about", "new-about", "new-session", 1)
        self._add_visit("post", "/post", "old-post", None, 1, tracking_version=None)
        db.session.commit()
        self.client.post("/auth/login", data={"email": admin.email, "password": "Password123"})

        new_export = self.client.get("/analytics/export.csv?dataset=pages&range=24h")
        previous_export = self.client.get("/analytics/export.csv?dataset=previous&range=24h")
        dashboard = self.client.get("/analytics?range=24h")

        self.assertEqual(new_export.status_code, 200)
        self.assertIn(b"About,1,", new_export.data)
        self.assertIn(b"Posts,0,", new_export.data)
        self.assertIn(b"Posts,1,", previous_export.data)
        self.assertIn(b"Previous analytics", dashboard.data)
        self.assertIn(b"1 visits collected before the new analytics version", dashboard.data)

    def test_acquisition_is_aggregated_and_exports_exclude_identifiers(self):
        admin = self._create_user("admin@ethz.ch", "admin-user")
        self._add_visit(
            "index", "/", "qr-home", "qr-session", 3,
            acquisition_source="campus-poster",
            acquisition_medium="qr",
            acquisition_campaign="welcome-week",
        )
        self._add_visit(
            "onboarding", "/onboarding", "qr-onboarding", "qr-session", 2,
            acquisition_source="campus-poster",
            acquisition_medium="qr",
            acquisition_campaign="welcome-week",
        )
        db.session.commit()
        self.client.post("/auth/login", data={"email": admin.email, "password": "Password123"})

        response = self.client.get("/analytics/export.csv?dataset=acquisition&range=24h")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn(b"QR code,1,100.0", response.data)
        self.assertIn(b"campus-poster", response.data)
        self.assertNotIn(b"qr-session", response.data)
        self.assertNotIn(b"admin@ethz.ch", response.data)

    def test_tracking_discards_query_string_and_invalid_attribution(self):
        self.client.post(
            "/analytics/page-visit",
            json={
                "page_key": "index",
                "path": "/?utm_medium=email&private=value",
                "duration_ms": 1000,
                "visit_token": "privacy-visit",
                "session_token": "privacy-session",
                "device_type": "desktop",
                "acquisition_source": "bad/value",
                "acquisition_medium": "email",
                "referrer_domain": "example.org/path",
            },
        )

        visit = PageVisit.query.one()
        self.assertEqual(visit.path, "/")
        self.assertIsNone(visit.acquisition_source)
        self.assertEqual(visit.acquisition_medium, "email")
        self.assertIsNone(visit.referrer_domain)


if __name__ == "__main__":
    unittest.main()
