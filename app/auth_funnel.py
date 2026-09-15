import secrets
from datetime import datetime, timedelta, timezone

from flask import session

from . import db
from .models import AuthFunnelAttempt


SESSION_KEY = "auth_funnel_attempt_id"
ABANDONED_AFTER = timedelta(minutes=30)
VALID_ACTIONS = {"post", "reply", "relate", "protected_page"}


def _utc_aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def start_auth_funnel(action):
    if action not in VALID_ACTIONS:
        action = "protected_page"

    existing_id = session.get(SESSION_KEY)
    if existing_id:
        existing = db.session.get(AuthFunnelAttempt, existing_id)
        if (
            existing is not None
            and existing.completed_at is None
            and existing.action == action
            and _utc_aware(existing.started_at) >= datetime.now(timezone.utc) - ABANDONED_AFTER
        ):
            return existing

    attempt = AuthFunnelAttempt(
        attempt_token=secrets.token_urlsafe(32),
        action=action,
    )
    db.session.add(attempt)
    db.session.commit()
    session[SESSION_KEY] = attempt.id
    session.modified = True
    return attempt


def mark_auth_funnel_profile_required():
    attempt_id = session.get(SESSION_KEY)
    attempt = db.session.get(AuthFunnelAttempt, attempt_id) if attempt_id else None
    if attempt is None or attempt.completed_at is not None:
        return
    now = datetime.now(timezone.utc)
    attempt.authenticated_at = attempt.authenticated_at or now
    attempt.profile_required_at = attempt.profile_required_at or now
    db.session.commit()


def complete_auth_funnel(user=None):
    attempt_id = session.pop(SESSION_KEY, None)
    if not attempt_id:
        return
    attempt = db.session.get(AuthFunnelAttempt, attempt_id)
    if attempt is None:
        return
    if user is not None and user.is_administrator():
        db.session.delete(attempt)
        db.session.commit()
        return
    now = datetime.now(timezone.utc)
    attempt.authenticated_at = attempt.authenticated_at or now
    attempt.completed_at = now
    db.session.commit()
