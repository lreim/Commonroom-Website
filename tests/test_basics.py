import unittest
from flask import current_app
from app import create_app, db
from config import ProductionConfig

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

    def test_production_cookies_are_secure(self):
        self.assertTrue(ProductionConfig.SESSION_COOKIE_SECURE)
        self.assertTrue(ProductionConfig.REMEMBER_COOKIE_SECURE)

    def test_socketio_is_not_wildcard_open(self):
        self.assertIsNone(current_app.config['TALKTO_SITE_ORIGIN'])

    def test_privacy_summaries_explain_oidc_and_e2ee_limit(self):
        client = self.app.test_client()

        onboarding = client.get('/onboarding')
        self.assertEqual(onboarding.status_code, 200)
        self.assertIn(b'Verified for access. Anonymous in the room.', onboarding.data)
        self.assertEqual(onboarding.data.count(b'class="privacy-not-emphasis"'), 4)
        self.assertIn(b'No name, institutional email address, or public university identifier.', onboarding.data)
        self.assertIn(b'not end-to-end encrypted', onboarding.data)
        self.assertIn(b'Matching profiles', onboarding.data)
        self.assertIn(b'Other profile tags', onboarding.data)
        self.assertNotIn(b'Existing Tags', onboarding.data)
        self.assertIn(b'exam stress and making a realistic study plan', onboarding.data)
        self.assertNotIn(b'career uncertainty', onboarding.data)

        privacy = client.get('/data-and-privacy')
        self.assertEqual(privacy.status_code, 200)
        self.assertIn(b'Your anonymity, quickly explained', privacy.data)
        self.assertEqual(privacy.data.count(b'class="privacy-not-emphasis"'), 17)
        self.assertIn(b'pairwise', privacy.data)
        self.assertIn(b'privacy-not-emphasis">not</em> currently end-to-end encrypted', privacy.data)
        self.assertIn(b'More details', privacy.data)
        self.assertEqual(privacy.data.count(b'<details class="privacy-detail'), 5)
        self.assertIn(b'does <em class="privacy-not-emphasis">not</em> use advertising trackers', privacy.data)
        self.assertIn(b'data-open-contact-panel', privacy.data)
        contact_handler_start = privacy.data.index(b'document.querySelectorAll("[data-open-contact-panel]")')
        contact_handler_end = privacy.data.index(b'panels.forEach(function (panel)', contact_handler_start)
        self.assertIn(b'event.stopPropagation();', privacy.data[contact_handler_start:contact_handler_end])
        self.assertIn(b'Last updated: September 2026', privacy.data)
        self.assertNotIn(b'Several important actions use signed tokens', privacy.data)
        self.assertNotIn(b'Keep me logged in', privacy.data)
        self.assertNotIn(b'Accounts created before edu-ID', privacy.data)

    def test_mobile_scroll_preview_script_is_landing_page_only(self):
        client = self.app.test_client()

        landing = client.get('/')
        self.assertIn(b'landing_scroll_previews.js', landing.data)

        onboarding = client.get('/onboarding')
        privacy = client.get('/data-and-privacy')
        self.assertNotIn(b'landing_scroll_previews.js', onboarding.data)
        self.assertNotIn(b'landing_scroll_previews.js', privacy.data)

    def test_landing_page_has_visible_explore_posts_button(self):
        response = self.app.test_client().get('/')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="homepage-explore-posts-button"', response.data)
        self.assertIn(b'Explore all posts', response.data)

    def test_onboarding_uses_real_profile_and_chat_structures(self):
        response = self.app.test_client().get('/onboarding')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'profile-page-header', response.data)
        self.assertIn(b'profile-page-details', response.data)
        self.assertIn(b'chat-detail-conversation-panel', response.data)
        self.assertNotIn(b'Private Chats', response.data)
        self.assertNotIn(b'Back to chats', response.data)
        self.assertIn(b'Write a message...', response.data)
        self.assertIn(b'id="onboarding-threads"', response.data)
        self.assertIn(b'Reply to original post', response.data)
        self.assertIn(b'Follow-up question', response.data)
        self.assertIn(b'Confession', response.data)

    def test_posts_page_has_dismissible_versioned_thread_update(self):
        response = self.app.test_client().get('/post')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-post-update-banner', response.data)
        self.assertIn(b'Follow conversations and choose how you want to reply.', response.data)
        self.assertIn(b'commonroom:update:interactive-threads-v1:dismissed', response.data)
        self.assertIn(b'window.localStorage.setItem', response.data)

    def test_rules_page_groups_overlapping_rules_without_dropping_topics(self):
        response = self.app.test_client().get('/rules')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Consent and boundaries', response.data)
        self.assertIn(b'Keep CommonRoom what it is', response.data)
        self.assertIn(b'What happens in the room stays in the room', response.data)
        self.assertIn(b'Be a decent human :)', response.data)
        self.assertIn(b'You do not have to fix anyone', response.data)
        self.assertIn(b'Know when CommonRoom is not enough', response.data)
        self.assertIn(b'See something that does not belong here?', response.data)
        self.assertIn(b'id="rules-report"', response.data)
        self.assertIn(b'data-floating-hint-reveal-target="rules-report"', response.data)
        self.assertIn(b'data-floating-hint-repeat', response.data)
        self.assertIn(b'Report it here', response.data)
