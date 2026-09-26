import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from io import StringIO
from math import sqrt
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import func
from sqlalchemy.orm import aliased
from flask import Response, abort, render_template, session, redirect, url_for, current_app, request, flash, jsonify
from . import main
from .forms import PostForm, ReplyForm, EditPostForm, StarterPostForm, EditProfileForm, EditProfileAdminForm, FeedbackForm
from .. import db, csrf
from ..models import (
    AuthFunnelAttempt,
    User,
    Post,
    Role,
    Tag,
    Conversation,
    PageVisit,
    PostThreadSubscription,
    PostThreadVisit,
    post_likes,
)
from ..tag_matching import match_tags, get_model
from flask_login import login_required, current_user
from app.decorators import admin_required, permission_required
from ..models import Permission
from ..email import send_email
from ..security import is_safe_local_redirect_target
from ..admin_demo import is_admin_demo_mode, set_admin_demo_mode
from ..notifications import mark_post_thread_visited, unread_reply_threads_for_user

#ATTENTION: with blueprint use main. iinstead of app. 

TRACKED_NAVBAR_PAGES = {
    "index": "Home",
    "about": "About",
    "onboarding": "Onboarding",
    "rules": "Rules",
    "feedback": "Feedback",
    "tag_search": "Tagsearch",
    "chat_index": "Chats",
    "post": "Posts",
    "get_help_now": "Get Help Now",
    "data_and_privacy": "Data and Privacy",
}

TRACKED_PAGE_PATH_PREFIXES = {
    "index": ["/"],
    "about": ["/about"],
    "onboarding": ["/onboarding"],
    "rules": ["/rules"],
    "feedback": ["/feedback"],
    "tag_search": ["/tags"],
    "chat_index": ["/chat"],
    "post": ["/post"],
    "get_help_now": ["/get-help-now"],
    "data_and_privacy": ["/data-and-privacy"],
}

MAX_TRACKED_VISIT_SECONDS = 60 * 60 * 4
VALID_DEVICE_TYPES = {"mobile", "desktop"}
CURRENT_ANALYTICS_VERSION = 2
ANALYTICS_EXPORT_DATASETS = {"summary", "pages", "hours", "journeys", "acquisition", "funnel", "previous"}
ANALYTICS_TRAFFIC_SEGMENTS = {
    "lecture_ersties": {
        "key": "lecture_ersties",
        "label": "Erstie lecture QR",
        "source": "lecture_ersties",
        "medium": "qr",
        "campaign": "launch_2026_09",
    },
}


def _analytics_client_token():
    token = session.get("analytics_client_token")
    if not token:
        token = uuid4().hex
        session["analytics_client_token"] = token
    return token


def _compute_chat_count_stats():
    users = User.query.all()
    conversation_counts = {user.id: 0 for user in users}

    for conversation in Conversation.query.all():
        conversation_counts[conversation.user_a_id] = conversation_counts.get(conversation.user_a_id, 0) + 1
        conversation_counts[conversation.user_b_id] = conversation_counts.get(conversation.user_b_id, 0) + 1

    counts = list(conversation_counts.values())
    if not counts:
        return {
            "max_chats_per_user": 0,
            "chat_count_std_dev": 0.0,
            "user_count": 0,
        }

    mean = sum(counts) / len(counts)
    variance = sum((count - mean) ** 2 for count in counts) / len(counts)
    return {
        "max_chats_per_user": max(counts),
        "chat_count_std_dev": sqrt(variance),
        "user_count": len(counts),
    }


def _tracked_page_visits_query():
    return (
        PageVisit.query
        .outerjoin(User, PageVisit.user_id == User.id)
        .outerjoin(Role, User.role_id == Role.id)
        .filter(
            (PageVisit.user_id.is_(None)) |
            (Role.name.is_(None)) |
            (Role.name != 'Administrator')
        )
    )


def _analytics_request_has_same_origin():
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    allowed_host = urlparse(request.host_url).netloc

    for candidate in (origin, referer):
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.netloc != allowed_host:
            return False
    return True


def _path_matches_tracked_page(page_key, path):
    prefixes = TRACKED_PAGE_PATH_PREFIXES.get(page_key, [])
    return any(path == prefix or path.startswith(f"{prefix}/") or path.startswith(f"{prefix}?") for prefix in prefixes)


def _sanitize_analytics_label(value, max_length):
    value = (value or "").strip().lower()
    if not value or len(value) > max_length:
        return None
    if value[0] in "=+-@":
        return None
    if any(not (character.isalnum() or character in " ._:-") for character in value):
        return None
    return value


def _sanitize_referrer_domain(value):
    value = (value or "").strip().lower().rstrip(".")
    if not value or len(value) > 255:
        return None
    if not value[0].isalnum():
        return None
    if any(not (character.isalnum() or character in ".-") for character in value):
        return None
    return value


def _validated_analytics_session_token(value):
    token = (value or "").strip()
    if (
        not token
        or len(token) > 64
        or any(not (character.isalnum() or character in "-_") for character in token)
    ):
        return None
    return token


def _build_visit_timeline(range_key, visits_query=None):
    now = datetime.now(timezone.utc)
    local_timezone = ZoneInfo("Europe/Zurich")
    if range_key == "24h":
        bucket_count = 24
        bucket_size = timedelta(hours=1)
        current_bucket_start = now.replace(minute=0, second=0, microsecond=0)
        label_format = "%H:%M"
    elif range_key == "1m":
        bucket_count = 30
        bucket_size = timedelta(days=1)
        current_bucket_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label_format = "%b %d"
    else:
        range_key = "1w"
        bucket_count = 7
        bucket_size = timedelta(days=1)
        current_bucket_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label_format = "%a"

    first_bucket_start = current_bucket_start - bucket_size * (bucket_count - 1)
    visits = (
        (visits_query if visits_query is not None else _tracked_page_visits_query())
        .filter(PageVisit.started_at >= first_bucket_start)
        .order_by(PageVisit.started_at.asc())
        .all()
    )

    counts_by_index = {index: 0 for index in range(bucket_count)}
    for visit in visits:
        started_at = visit.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        delta = started_at - first_bucket_start
        index = int(delta.total_seconds() // bucket_size.total_seconds())
        if 0 <= index < bucket_count:
            counts_by_index[index] += 1

    points = []
    max_count = max(counts_by_index.values()) if counts_by_index else 0
    for index in range(bucket_count):
        bucket_start = first_bucket_start + bucket_size * index
        points.append(
            {
                "label": bucket_start.astimezone(local_timezone).strftime(label_format),
                "count": counts_by_index[index],
            }
        )

    return {
        "range_key": range_key,
        "points": points,
        "max_count": max_count,
        "total_visits": sum(point["count"] for point in points),
        "first_bucket_start": first_bucket_start,
        "timezone": "Europe/Zurich",
    }


def _build_hour_distribution(visits):
    local_timezone = ZoneInfo("Europe/Zurich")
    counts = [0] * 24
    for visit in visits:
        started_at = visit.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        counts[started_at.astimezone(local_timezone).hour] += 1

    max_count = max(counts) if counts else 0
    return {
        "timezone": "Europe/Zurich",
        "max_count": max_count,
        "total_visits": sum(counts),
        "points": [
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "count": count,
            }
            for hour, count in enumerate(counts)
        ],
    }


def _build_journey_stats(visits):
    visits_by_session = defaultdict(list)
    for visit in visits:
        if visit.session_token:
            visits_by_session[visit.session_token].append(visit)

    first_step_counts = Counter()
    path_counts = Counter()
    home_session_count = 0

    for session_visits in visits_by_session.values():
        ordered_visits = sorted(session_visits, key=lambda visit: (visit.started_at, visit.id))
        page_keys = []
        for visit in ordered_visits:
            if not page_keys or page_keys[-1] != visit.page_key:
                page_keys.append(visit.page_key)

        try:
            home_index = page_keys.index("index")
        except ValueError:
            continue

        pages_after_home = [page_key for page_key in page_keys[home_index + 1:] if page_key != "index"]
        if not pages_after_home:
            continue

        home_session_count += 1
        first_step_counts[pages_after_home[0]] += 1
        path_keys = tuple(["index"] + pages_after_home[:2])
        path_counts[path_keys] += 1

    def page_name(page_key):
        return TRACKED_NAVBAR_PAGES.get(page_key, page_key.replace("_", " ").title())

    first_steps = [
        {
            "page_key": page_key,
            "page_name": page_name(page_key),
            "count": count,
            "percent": round(count / home_session_count * 100, 1) if home_session_count else 0.0,
        }
        for page_key, count in first_step_counts.most_common()
    ]
    paths = [
        {
            "label": " → ".join(page_name(page_key) for page_key in path_keys),
            "count": count,
        }
        for path_keys, count in path_counts.most_common(10)
    ]

    return {
        "tracked_sessions": len(visits_by_session),
        "home_sessions_with_next_page": home_session_count,
        "first_steps": first_steps,
        "paths": paths,
    }


def _build_page_stats(visits_query):
    page_rows = (
        visits_query
        .with_entities(
            PageVisit.page_key,
            PageVisit.user_id,
            func.count(PageVisit.id).label("visit_count"),
            func.sum(PageVisit.duration_seconds).label("total_duration_seconds"),
        )
        .group_by(PageVisit.page_key, PageVisit.user_id)
        .all()
    )
    page_row_map = {}
    for row in page_rows:
        bucket = page_row_map.setdefault(
            row.page_key,
            {
                "logged_in_visits": 0,
                "logged_in_total_duration_seconds": 0,
                "public_visits": 0,
                "public_total_duration_seconds": 0,
            },
        )
        audience = "public" if row.user_id is None else "logged_in"
        bucket[f"{audience}_visits"] += int(row.visit_count or 0)
        bucket[f"{audience}_total_duration_seconds"] += int(row.total_duration_seconds or 0)

    page_stats = []
    for page_key, page_name in TRACKED_NAVBAR_PAGES.items():
        row = page_row_map.get(page_key, {})
        logged_in_visits = row.get("logged_in_visits", 0)
        public_visits = row.get("public_visits", 0)
        logged_in_duration = row.get("logged_in_total_duration_seconds", 0)
        public_duration = row.get("public_total_duration_seconds", 0)
        total_visits = logged_in_visits + public_visits
        total_duration = logged_in_duration + public_duration
        page_stats.append(
            {
                "page_key": page_key,
                "page_name": page_name,
                "visit_count": total_visits,
                "avg_duration_seconds": round(total_duration / total_visits, 1) if total_visits else 0.0,
                "total_duration_seconds": total_duration,
                "logged_in_visits": logged_in_visits,
                "logged_in_avg_duration_seconds": round(logged_in_duration / logged_in_visits, 1) if logged_in_visits else 0.0,
                "logged_in_total_duration_seconds": logged_in_duration,
                "public_visits": public_visits,
                "public_avg_duration_seconds": round(public_duration / public_visits, 1) if public_visits else 0.0,
                "public_total_duration_seconds": public_duration,
            }
        )
    page_stats.sort(key=lambda item: (-item["visit_count"], item["page_name"].lower()))
    return page_stats


def _build_visit_splits(visits_query):
    device_stats = {"mobile": 0, "desktop": 0}
    device_rows = (
        visits_query
        .with_entities(PageVisit.device_type, func.count(PageVisit.id).label("visit_count"))
        .group_by(PageVisit.device_type)
        .all()
    )
    for row in device_rows:
        if row.device_type in device_stats:
            device_stats[row.device_type] = int(row.visit_count or 0)
    auth_stats = {
        "logged_in": visits_query.filter(PageVisit.user_id.isnot(None)).count(),
        "public": visits_query.filter(PageVisit.user_id.is_(None)).count(),
    }
    return device_stats, auth_stats


def _build_acquisition_stats(visits):
    first_visit_by_session = {}
    for visit in sorted(visits, key=lambda item: (item.started_at, item.id)):
        session_key = visit.session_token or f"visit-{visit.id}"
        first_visit_by_session.setdefault(session_key, visit)

    channel_counts = Counter()
    source_counts = Counter()
    campaign_counts = Counter()
    for visit in first_visit_by_session.values():
        medium = (visit.acquisition_medium or "direct").lower()
        source = (visit.acquisition_source or "direct").lower()
        if medium == "qr":
            channel = "QR code"
        elif medium in {"email", "newsletter"}:
            channel = "Email / newsletter"
        elif medium == "referral":
            channel = "External referral"
        elif medium == "direct" and source == "direct":
            channel = "Direct"
        else:
            channel = "Other campaign"
        channel_counts[channel] += 1
        source_counts[f"{source} · {medium}"] += 1
        if visit.acquisition_campaign:
            campaign_counts[visit.acquisition_campaign] += 1

    channel_order = ["Direct", "Email / newsletter", "QR code", "External referral", "Other campaign"]
    total_sessions = len(first_visit_by_session)
    channels = [
        {
            "label": label,
            "count": channel_counts[label],
            "percent": round(channel_counts[label] / total_sessions * 100, 1) if total_sessions else 0.0,
        }
        for label in channel_order
    ]
    sources = [{"label": label, "count": count} for label, count in source_counts.most_common(10)]
    campaigns = [{"label": label, "count": count} for label, count in campaign_counts.most_common(10)]
    return {
        "total_sessions": total_sessions,
        "channels": channels,
        "sources": sources,
        "campaigns": campaigns,
    }


def _build_content_stats():
    root_posts = Post.query.filter(Post.parent_id.is_(None)).all()
    root_post_count = len(root_posts)
    relate_post_count = Post.query.filter(Post.parent_id.is_(None), Post.post_type == "relate").count()
    question_post_count = Post.query.filter(Post.parent_id.is_(None), Post.post_type == "question").count()
    confession_post_count = Post.query.filter(Post.parent_id.is_(None), Post.post_type == "confession").count()
    reply_count = Post.query.filter(Post.parent_id.isnot(None)).count()
    replied_post_count = sum(post.replies.count() > 0 for post in root_posts)
    profile_query = (
        User.query
        .outerjoin(Role, User.role_id == Role.id)
        .filter((Role.name.is_(None)) | (Role.name != "Administrator"))
    )
    profile_count = profile_query.count()
    profiles_with_contact_email = profile_query.filter(
        User.contact_email.isnot(None),
        func.length(func.trim(User.contact_email)) > 0,
    ).count()
    chat_stats = _compute_chat_count_stats()
    return {
        "total_root_posts": root_post_count,
        "relate_post_count": relate_post_count,
        "question_post_count": question_post_count,
        "confession_post_count": confession_post_count,
        "replied_post_count": replied_post_count,
        "unreplied_post_count": max(root_post_count - replied_post_count, 0),
        "total_replies": reply_count,
        "total_posts_including_replies": root_post_count + reply_count,
        "reply_rate": round(replied_post_count / root_post_count * 100, 1) if root_post_count else 0.0,
        "total_profiles": profile_count,
        "profiles_with_contact_email": profiles_with_contact_email,
        "profiles_without_contact_email": max(profile_count - profiles_with_contact_email, 0),
        "total_conversations": Conversation.query.count(),
        "max_chats_per_user": chat_stats["max_chats_per_user"],
        "chat_count_std_dev": round(chat_stats["chat_count_std_dev"], 2),
        "tracked_user_count": chat_stats["user_count"],
    }


def _build_auth_funnel_stats(first_bucket_start):
    attempts = (
        AuthFunnelAttempt.query
        .filter(AuthFunnelAttempt.started_at >= first_bucket_start)
        .order_by(AuthFunnelAttempt.started_at.asc(), AuthFunnelAttempt.id.asc())
        .all()
    )
    abandoned_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    labels = {
        "post": "Write a post",
        "reply": "Reply",
        "relate": "Relate",
        "protected_page": "Protected page",
    }
    action_rows = {
        action: {"action": action, "label": label, "started": 0, "completed": 0, "abandoned": 0}
        for action, label in labels.items()
    }
    totals = {
        "started": len(attempts),
        "completed": 0,
        "login_abandoned": 0,
        "profile_abandoned": 0,
        "in_progress": 0,
    }

    for attempt in attempts:
        row = action_rows.get(attempt.action, action_rows["protected_page"])
        row["started"] += 1
        started_at = attempt.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        if attempt.completed_at is not None:
            totals["completed"] += 1
            row["completed"] += 1
            continue

        profile_required_at = attempt.profile_required_at
        if profile_required_at is not None:
            if profile_required_at.tzinfo is None:
                profile_required_at = profile_required_at.replace(tzinfo=timezone.utc)
            if profile_required_at <= abandoned_cutoff:
                totals["profile_abandoned"] += 1
                row["abandoned"] += 1
            else:
                totals["in_progress"] += 1
        elif started_at <= abandoned_cutoff:
            totals["login_abandoned"] += 1
            row["abandoned"] += 1
        else:
            totals["in_progress"] += 1

    totals["completion_rate"] = (
        round(totals["completed"] / totals["started"] * 100, 1)
        if totals["started"] else 0.0
    )
    totals["actions"] = list(action_rows.values())
    totals["abandoned_after_minutes"] = 30
    return totals


def _build_analytics_snapshot(selected_range, segment_key=None):
    selected_segment = ANALYTICS_TRAFFIC_SEGMENTS.get(segment_key)
    current_query = _tracked_page_visits_query().filter(
        PageVisit.tracking_version == CURRENT_ANALYTICS_VERSION
    )
    if selected_segment is not None:
        current_query = current_query.filter(
            PageVisit.acquisition_source == selected_segment["source"],
            PageVisit.acquisition_medium == selected_segment["medium"],
            PageVisit.acquisition_campaign == selected_segment["campaign"],
        )
    visit_timeline = _build_visit_timeline(selected_range, current_query)
    selected_range = visit_timeline["range_key"]
    visits_in_range_query = current_query.filter(
        PageVisit.started_at >= visit_timeline["first_bucket_start"]
    )
    visits_in_range = visits_in_range_query.order_by(PageVisit.started_at.asc(), PageVisit.id.asc()).all()
    page_stats = _build_page_stats(visits_in_range_query)
    device_stats, auth_stats = _build_visit_splits(visits_in_range_query)

    previous_query = _tracked_page_visits_query().filter(PageVisit.tracking_version.is_(None))
    previous_page_stats = _build_page_stats(previous_query)
    previous_device_stats, previous_auth_stats = _build_visit_splits(previous_query)
    previous_analytics = {
        "total_visits": previous_query.count(),
        "page_stats": previous_page_stats,
        "device_stats": previous_device_stats,
        "auth_stats": previous_auth_stats,
    }

    snapshot = {
        "page_stats": page_stats,
        "max_page_visits": max((item["visit_count"] for item in page_stats), default=0),
        "device_stats": device_stats,
        "auth_stats": auth_stats,
        "visit_timeline": visit_timeline,
        "selected_range": selected_range,
        "selected_segment": selected_segment,
        "selected_segment_key": selected_segment["key"] if selected_segment else None,
        "traffic_segments": list(ANALYTICS_TRAFFIC_SEGMENTS.values()),
        "tracked_page_count": sum(1 for item in page_stats if item["visit_count"] > 0),
        "hour_distribution": _build_hour_distribution(visits_in_range),
        "journey_stats": _build_journey_stats(visits_in_range),
        "acquisition_stats": _build_acquisition_stats(visits_in_range),
        "auth_funnel_stats": _build_auth_funnel_stats(visit_timeline["first_bucket_start"]),
        "previous_analytics": previous_analytics,
    }
    snapshot.update(_build_content_stats())
    return snapshot

#routes (view functions sind die index() etc.) for every page I have: @login_required before route to make it safe
#für externe Inhalte, mails, magic links nutze external=True
#The methods argument added to the app.route decorator tells Flask to register the view
#function as a handler for GET and POST requests in the URL map. When methods is not
#given, the view function is registered to handle GET requests only.
@main.route('/')
def index():
    return render_template('index.html', active_page='index', current_time=datetime.now(timezone.utc))

@main.route('/settings')
@login_required
def settings():
    user = current_user._get_current_object()
    return render_template('settings.html', active_page='settings', user=user)


@main.route('/about')
def about():
    return render_template('about.html', active_page='about')

@main.route('/onboarding')
def onboarding():
    return render_template('onboarding.html', active_page='onboarding')

@main.route('/rules')
def rules():
    return render_template('rules.html', active_page='rules')

@main.route('/data-and-privacy')
def data_and_privacy():
    return render_template('data_and_privacy.html', active_page='data_and_privacy')


@main.route('/feedback', methods=['GET', 'POST'])
def feedback():
    form = FeedbackForm()
    if form.validate_on_submit():
        send_email(
            'contact@commonroom.ch',
            'Test phase feedback',
            'feedback/email/feedback',
            message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_FEEDBACK'),
            category=form.category.data,
            feedback_type=form.feedback_type.data,
            allow_follow_up=form.allow_follow_up.data,
            message=form.message.data,
            is_authenticated=current_user.is_authenticated,
            user=current_user._get_current_object() if current_user.is_authenticated else None,
        )
        flash('Your feedback has been sent. Thanks for helping improve CommonRoom.')
        return redirect(url_for('main.feedback'))
    return render_template('feedback.html', form=form, active_page='feedback')


@main.route('/analytics/page-visit', methods=['POST'])
@csrf.exempt
def track_page_visit():
    if not _analytics_request_has_same_origin():
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    session_token = _validated_analytics_session_token(payload.get("session_token"))
    if current_user.is_authenticated and current_user.is_administrator():
        if session_token:
            PageVisit.query.filter_by(
                session_token=session_token,
                user_id=None,
            ).delete(synchronize_session=False)
            db.session.commit()
        return ("", 204)

    page_key = (payload.get("page_key") or "").strip()
    path = (payload.get("path") or request.path or "").strip()
    duration_ms = payload.get("duration_ms", 0)
    visit_token = (payload.get("visit_token") or "").strip()
    device_type = (payload.get("device_type") or "desktop").strip().lower()
    acquisition_source = _sanitize_analytics_label(payload.get("acquisition_source"), 80)
    acquisition_medium = _sanitize_analytics_label(payload.get("acquisition_medium"), 40)
    acquisition_campaign = _sanitize_analytics_label(payload.get("acquisition_campaign"), 100)
    referrer_domain = _sanitize_referrer_domain(payload.get("referrer_domain"))

    if page_key not in TRACKED_NAVBAR_PAGES:
        return ("", 204)
    if device_type not in VALID_DEVICE_TYPES:
        device_type = "desktop"

    try:
        duration_ms = max(int(duration_ms), 0)
    except (TypeError, ValueError):
        duration_ms = 0

    duration_seconds = min(int(round(duration_ms / 1000.0)), MAX_TRACKED_VISIT_SECONDS)
    if duration_seconds < 0:
        duration_seconds = 0

    if not visit_token:
        visit_token = f"{_analytics_client_token()}-{uuid4().hex}"

    if len(visit_token) > 64:
        visit_token = visit_token[:64]

    normalized_path = urlparse(path[:255]).path or "/"
    if not _path_matches_tracked_page(page_key, normalized_path):
        return ("", 204)

    existing_visit = PageVisit.query.filter_by(visit_token=visit_token).first()
    if existing_visit is not None:
        return ("", 204)

    ended_at = datetime.now(timezone.utc)
    started_at = ended_at
    if duration_seconds > 0:
        started_at = ended_at - timedelta(seconds=duration_seconds)

    visit = PageVisit(
        page_key=page_key,
        path=normalized_path,
        device_type=device_type,
        visit_token=visit_token,
        session_token=session_token,
        tracking_version=CURRENT_ANALYTICS_VERSION,
        acquisition_source=acquisition_source,
        acquisition_medium=acquisition_medium,
        acquisition_campaign=acquisition_campaign,
        referrer_domain=referrer_domain,
        user_id=current_user.id if current_user.is_authenticated else None,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
    )
    db.session.add(visit)
    db.session.commit()
    return ("", 204)

@main.route('/post', methods=['GET', 'POST'])
def post():
    form = PostForm()
    reply_form = ReplyForm()
    reply_to_id = request.form.get('reply_to_id', type=int)
    if request.method == 'POST' and not current_user.is_authenticated:
        return_path = request.full_path if request.query_string else request.path
        intent = 'reply' if reply_to_id else 'post'
        return redirect(url_for('auth.login', next=return_path, intent=intent))
    submitted_form = reply_form if reply_to_id else form
    if submitted_form.validate_on_submit():
        parent_post = None
        if reply_to_id:
            parent_post = Post.query.get_or_404(reply_to_id)
            if parent_post.parent is not None:
                parent_post = parent_post.parent
        # The Admin identity is only used for root-level starter posts. Replies
        # always belong to the signed-in personal profile so their author can
        # edit them normally afterwards.
        posting_as_admin = is_admin_demo_mode() and parent_post is None
        post = Post(
            body=submitted_form.body.data,
            author_id=None if posting_as_admin else current_user.id,
            parent=parent_post,
            post_type=parent_post.post_type if parent_post is not None else form.post_type.data,
            is_starter=posting_as_admin,
        )
        db.session.add(post)
        db.session.commit()
        if parent_post is not None:
            return redirect(url_for('main.post_thread', post_id=parent_post.id))
        return redirect(url_for('main.post'))

    all_tags = Tag.library_names()
    topic_query = request.args.get('topics', '', type=str).strip()
    selected_topics = []
    seen_topics = set()
    for chunk in topic_query.split(','):
        topic = chunk.strip().lower()
        if not topic or topic in seen_topics:
            continue
        seen_topics.add(topic)
        selected_topics.append(topic)

    matched_topics = []
    if topic_query:
        matched_topics = [item["name"] for item in match_tags(topic_query, all_tags)]

    sort_by = request.args.get('sort', 'latest_activity', type=str)
    if sort_by not in {
        'latest_activity',
        'most_recent',
        'most_replies',
        'most_relatable',
        'oldest_first',
        'unanswered',
        'still_thinking',
    }:
        sort_by = 'latest_activity'
    post_type_filter = request.args.get('type', 'all', type=str).lower()
    if post_type_filter not in {'all', 'relate', 'question', 'confession'}:
        post_type_filter = 'all'
    page = request.args.get('page', 1, type=int)
    post_query = Post.query.filter(Post.parent_id.is_(None))
    if post_type_filter != 'all':
        post_query = post_query.filter(Post.post_type == post_type_filter)
    if matched_topics:
        post_query = post_query.join(User, Post.author).join(User.tags).filter(Tag.name.in_(matched_topics)).distinct()

    if sort_by == 'unanswered':
        post_query = (
            post_query
            .filter(~Post.replies.any())
            .order_by(Post.timestamp.desc(), Post.id.desc())
        )
    elif sort_by == 'still_thinking':
        post_query = (
            post_query
            .filter(Post.thread_status == 'still_thinking')
            .order_by(Post.timestamp.desc(), Post.id.desc())
        )
    elif sort_by == 'latest_activity':
        # Keep the root post and every nested reply in the same sortable thread.
        post_tree = (
            db.session.query(
                Post.id.label('post_id'),
                Post.id.label('root_post_id'),
                Post.timestamp.label('activity_at'),
            )
            .filter(Post.parent_id.is_(None))
            .cte('post_tree', recursive=True)
        )
        child = aliased(Post)
        post_tree = post_tree.union_all(
            db.session.query(
                child.id,
                post_tree.c.root_post_id,
                child.timestamp,
            ).filter(child.parent_id == post_tree.c.post_id)
        )
        latest_activity = (
            db.session.query(
                post_tree.c.root_post_id,
                func.max(post_tree.c.activity_at).label('latest_at'),
            )
            .group_by(post_tree.c.root_post_id)
            .subquery()
        )
        post_query = (
            post_query
            .join(latest_activity, Post.id == latest_activity.c.root_post_id)
            .order_by(latest_activity.c.latest_at.desc(), Post.id.desc())
        )
    elif sort_by == 'most_recent':
        post_query = post_query.order_by(Post.timestamp.desc(), Post.id.desc())
    elif sort_by == 'most_replies':
        reply_count_subquery = (
            db.session.query(
                Post.parent_id.label('root_post_id'),
                func.count(Post.id).label('reply_count'),
            )
            .filter(Post.parent_id.isnot(None))
            .group_by(Post.parent_id)
            .subquery()
        )
        post_query = (
            post_query
            .outerjoin(reply_count_subquery, Post.id == reply_count_subquery.c.root_post_id)
            .order_by(func.coalesce(reply_count_subquery.c.reply_count, 0).desc(), Post.timestamp.desc())
        )
    elif sort_by == 'most_relatable':
        like_count_subquery = (
            db.session.query(
                post_likes.c.post_id.label('liked_post_id'),
                func.count(post_likes.c.user_id).label('like_count'),
            )
            .group_by(post_likes.c.post_id)
            .subquery()
        )
        post_query = (
            post_query
            .outerjoin(like_count_subquery, Post.id == like_count_subquery.c.liked_post_id)
            .order_by(func.coalesce(like_count_subquery.c.like_count, 0).desc(), Post.timestamp.desc())
        )
    elif sort_by == 'oldest_first':
        post_query = post_query.order_by(Post.id.asc(), Post.timestamp.asc())
    pagination = post_query.paginate(
        page=page,
        per_page=current_app.config.get('TALKTO_POSTS_PER_PAGE', 20),
        error_out=False
    )
    posts = pagination.items
    new_post_ids = set()
    if current_user.is_authenticated:
        seen_root_ids = {
            int(post_id)
            for post_id in session.get('seen_post_thread_ids', [])
            if str(post_id).isdigit()
        }
        for root_post in posts:
            if root_post.id not in seen_root_ids:
                new_post_ids.add(root_post.id)
            visit = PostThreadVisit.query.filter_by(
                user_id=current_user.id,
                root_post_id=root_post.id,
            ).first()
            threshold = visit.last_visited_at if visit is not None else None
            if threshold is not None and threshold.tzinfo is None:
                threshold = threshold.replace(tzinfo=timezone.utc)
            frontier = list(root_post.replies.all())
            latest_reply = None
            while frontier:
                reply = frontier.pop()
                reply_at = reply.timestamp
                if reply_at.tzinfo is None:
                    reply_at = reply_at.replace(tzinfo=timezone.utc)
                if reply.author_id != current_user.id and (threshold is None or reply_at > threshold):
                    if latest_reply is None or reply_at > latest_reply:
                        latest_reply = reply_at
                frontier.extend(reply.replies.all())
            if latest_reply is not None:
                new_post_ids.add(root_post.id)
    return render_template(
        'post.html',
        form=form,
        reply_form=reply_form,
        posts=posts,
        new_post_ids=new_post_ids,
        pagination=pagination,
        all_tags=all_tags,
        selected_topics=', '.join(selected_topics),
        matched_topics=matched_topics,
        sort_by=sort_by,
        post_type_filter=post_type_filter,
        active_page='post',
    )


@main.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_post_like(post_id):
    post = Post.query.get_or_404(post_id)

    liked = post.is_liked_by(current_user)
    if liked:
        post.liked_by.remove(current_user)
    else:
        post.liked_by.append(current_user)
    db.session.commit()
    return jsonify({'liked': not liked, 'count': post.liked_by.count()})


@main.route('/post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def post_thread(post_id):
    root_post = Post.query.get_or_404(post_id)
    if root_post.parent is not None:
        while root_post.parent is not None:
            root_post = root_post.parent
        return redirect(url_for('main.post_thread', post_id=root_post.id))

    form = ReplyForm()
    reply_to_id = request.form.get('reply_to_id', type=int)
    failed_reply_to_id = None
    if request.method == 'POST':
        if not current_user.can(Permission.WRITE_ARTICLES):
            abort(403)
        if form.validate_on_submit():
            parent_post = root_post
            if reply_to_id:
                parent_post = Post.query.get_or_404(reply_to_id)
                ancestor = parent_post
                while ancestor.parent is not None:
                    ancestor = ancestor.parent
                if ancestor.id != root_post.id:
                    parent_post = root_post
            reply = Post(
                body=form.body.data,
                author_id=current_user.id,
                parent=parent_post,
                post_type=parent_post.post_type,
                reply_type=form.reply_type.data,
                is_starter=False,
            )
            db.session.add(reply)
            db.session.commit()
            flash('Your reply was posted.')
            return redirect(url_for(
                'main.post_thread',
                post_id=root_post.id,
                _anchor=f'post-{reply.id}',
            ))
        failed_reply_to_id = reply_to_id or root_post.id

    previous_visit = PostThreadVisit.query.filter_by(
        user_id=current_user.id,
        root_post_id=root_post.id,
    ).first()
    previous_visit_at = previous_visit.last_visited_at if previous_visit is not None else None

    mark_post_thread_visited(current_user.id, root_post.id)
    seen_thread_ids = {
        int(thread_id)
        for thread_id in session.get('seen_post_thread_ids', [])
        if str(thread_id).isdigit()
    }
    seen_thread_ids.add(root_post.id)
    session['seen_post_thread_ids'] = list(seen_thread_ids)
    session.modified = True

    thread_replies = []
    frontier = list(root_post.replies.all())
    visited_reply_ids = set()
    while frontier:
        reply = frontier.pop()
        if reply.id in visited_reply_ids:
            continue
        visited_reply_ids.add(reply.id)
        thread_replies.append(reply)
        frontier.extend(reply.replies.all())

    def reply_sort_key(reply):
        timestamp = reply.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp, reply.id

    thread_replies.sort(key=reply_sort_key)

    new_reply_ids = set()
    if previous_visit_at is not None:
        if previous_visit_at.tzinfo is None:
            previous_visit_at = previous_visit_at.replace(tzinfo=timezone.utc)
        new_reply_ids = {
            reply.id
            for reply in thread_replies
            if reply.author_id != current_user.id
            and reply_sort_key(reply)[0] > previous_visit_at
        }

    def descendants_for(reply):
        descendants = []
        frontier = list(reply.replies.all())
        seen = set()
        while frontier:
            child = frontier.pop()
            if child.id in seen:
                continue
            seen.add(child.id)
            descendants.append(child)
            frontier.extend(child.replies.all())
        descendants.sort(key=reply_sort_key)
        return descendants

    reply_groups = []
    for direct_reply in root_post.replies.all():
        replies = [direct_reply] + descendants_for(direct_reply)
        reply_groups.append(SimpleNamespace(replies=replies))

    reply_groups.sort(key=lambda group: reply_sort_key(group.replies[0]))

    all_thread_posts = [root_post] + thread_replies
    participant_count = len({
        thread_post.author_id
        for thread_post in all_thread_posts
        if thread_post.author_id is not None
    })
    latest_activity_at = max(reply_sort_key(thread_post)[0] for thread_post in all_thread_posts)
    subscription = PostThreadSubscription.query.filter_by(
        user_id=current_user.id,
        root_post_id=root_post.id,
    ).first()

    return render_template(
        'post_thread.html',
        post=root_post,
        form=form,
        thread_replies=thread_replies,
        reply_groups=reply_groups,
        participant_count=participant_count,
        latest_activity_at=latest_activity_at,
        new_reply_ids=new_reply_ids,
        is_following=subscription is not None,
        failed_reply_to_id=failed_reply_to_id,
        thread_status_labels={
            'looking_for_replies': 'Open / no status shown',
            'still_thinking': 'Still thinking about this',
            'answered': 'Answered',
        },
    )


@main.route('/post/<int:post_id>/follow', methods=['POST'])
@login_required
def toggle_post_thread_follow(post_id):
    root_post = Post.query.get_or_404(post_id)
    while root_post.parent is not None:
        root_post = root_post.parent
    subscription = PostThreadSubscription.query.filter_by(
        user_id=current_user.id,
        root_post_id=root_post.id,
    ).first()
    if subscription is None:
        db.session.add(PostThreadSubscription(
            user_id=current_user.id,
            root_post_id=root_post.id,
        ))
        flash('You will be notified about new replies in this thread.')
    else:
        db.session.delete(subscription)
        flash('Thread notifications are turned off.')
    db.session.commit()
    return redirect(url_for('main.post_thread', post_id=root_post.id))


@main.route('/post/<int:post_id>/status', methods=['POST'])
@login_required
def update_post_thread_status(post_id):
    root_post = Post.query.get_or_404(post_id)
    can_manage_status = (
        root_post.author_id == current_user.id
        or (root_post.is_starter and current_user.is_administrator())
    )
    if root_post.parent_id is not None or not can_manage_status:
        abort(403)
    status = request.form.get('thread_status', type=str)
    if status not in {'looking_for_replies', 'still_thinking', 'answered'}:
        abort(400)
    root_post.thread_status = status
    db.session.commit()
    flash('Thread status updated.')
    requested_return_url = request.form.get('next')
    if is_safe_local_redirect_target(requested_return_url):
        return redirect(requested_return_url)
    return redirect(url_for('main.post_thread', post_id=root_post.id))


@main.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post_to_edit = Post.query.get_or_404(post_id)
    if post_to_edit.is_starter:
        # Older Admin replies were stored as ownerless starter content. Keep
        # root starter posts in their dedicated editor, while allowing an
        # administrator to correct those existing replies.
        if post_to_edit.parent_id is None:
            abort(404)
        if not current_user.is_administrator():
            abort(403)
    elif post_to_edit.author_id != current_user.id:
        abort(403)

    requested_return_url = request.form.get('next') or request.args.get('next')
    return_url = (
        requested_return_url
        if is_safe_local_redirect_target(requested_return_url)
        else url_for('main.post')
    )
    if post_to_edit.parent_id is not None and not is_safe_local_redirect_target(requested_return_url):
        root_post = post_to_edit
        while root_post.parent is not None:
            root_post = root_post.parent
        return_url = url_for('main.post_thread', post_id=root_post.id)

    form = EditPostForm(obj=post_to_edit)
    if form.validate_on_submit():
        post_to_edit.body = form.body.data
        post_to_edit.edited_at = datetime.now(timezone.utc)
        db.session.add(post_to_edit)
        db.session.commit()
        flash('Your post has been updated.')
        return redirect(return_url)

    return render_template(
        'edit_post.html',
        form=form,
        post=post_to_edit,
        return_url=return_url,
        active_page='post',
    )


def _profile_activity_payload(posts, base_url, owner_user_id=None):
    activity_filter = request.args.get('activity', 'all', type=str).lower()
    if activity_filter not in {'all', 'posts', 'replies'}:
        activity_filter = 'all'
    activity_sort = request.args.get('sort', 'newest', type=str).lower()
    if activity_sort not in {'newest', 'oldest'}:
        activity_sort = 'newest'

    post_count = sum(post.parent_id is None for post in posts)
    reply_count = len(posts) - post_count
    if activity_filter == 'posts':
        visible_posts = [post for post in posts if post.parent_id is None]
    elif activity_filter == 'replies':
        visible_posts = [post for post in posts if post.parent_id is not None]
    else:
        visible_posts = list(posts)

    def aware_timestamp(post):
        value = post.timestamp
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    visible_posts.sort(
        key=lambda post: (aware_timestamp(post), post.id),
        reverse=activity_sort == 'newest',
    )
    week_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    groups = {'recent': [], 'earlier': []}
    for post in visible_posts:
        root_post = post
        while root_post.parent is not None:
            root_post = root_post.parent
        entry = {'post': post, 'root_post': root_post}
        group_key = 'recent' if aware_timestamp(post) >= week_cutoff else 'earlier'
        groups[group_key].append(entry)

    if (
        owner_user_id is not None
        and current_user.is_authenticated
        and current_user.id == owner_user_id
    ):
        unread_by_root = unread_reply_threads_for_user(current_user)
        entries_by_root = defaultdict(list)
        for entries in groups.values():
            for entry in entries:
                entries_by_root[entry['root_post'].id].append(entry)

        for root_id, unread in unread_by_root.items():
            candidates = entries_by_root.get(root_id, [])
            if not candidates:
                continue
            root_entry = next(
                (
                    entry for entry in candidates
                    if entry['post'].id == root_id
                    and entry['post'].author_id == owner_user_id
                ),
                None,
            )
            marker_entry = root_entry or max(
                candidates,
                key=lambda entry: (
                    aware_timestamp(entry['post']),
                    entry['post'].id,
                ),
            )
            marker_entry['unread_reply'] = unread

    return {
        'filter': activity_filter,
        'sort': activity_sort,
        'base_url': base_url,
        'total_count': len(posts),
        'post_count': post_count,
        'reply_count': reply_count,
        'visible_count': len(visible_posts),
        'groups': groups,
        'group_order': (
            [('recent', 'This week'), ('earlier', 'Earlier')]
            if activity_sort == 'newest'
            else [('earlier', 'Earlier'), ('recent', 'This week')]
        ),
    }

@main.route('/user/<username>')
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    return_to = request.args.get('return_to', type=str)
    posts = user.posts.filter_by(is_starter=False).order_by(Post.timestamp.desc()).all()
    recommend_profiles = request.args.get('recommend', 0, type=int) == 1
    recommended_users = []

    if (
        recommend_profiles
        and current_user.is_authenticated
        and user.id == current_user.id
    ):
        current_tag_names = {tag.name for tag in current_user.tags}
        if current_tag_names:
            candidates = User.query.filter(User.id != current_user.id).all()
            scored_users = []
            for candidate in candidates:
                candidate_tag_names = {tag.name for tag in candidate.tags}
                matching_tags = sorted(current_tag_names & candidate_tag_names)
                if matching_tags:
                    scored_users.append(
                        {
                            "user": candidate,
                            "matching_tags": matching_tags,
                            "match_count": len(matching_tags),
                        }
                    )
            scored_users.sort(
                key=lambda item: (-item["match_count"], item["user"].username.lower())
            )
            recommended_users = scored_users[:4]

    return render_template(
        'user.html',
        user=user,
        posts=posts,
        activity=_profile_activity_payload(
            posts,
            url_for('main.user', username=user.username),
            owner_user_id=user.id,
        ),
        return_to=return_to if is_safe_local_redirect_target(return_to) else None,
        recommend_profiles=recommend_profiles,
        recommended_users=recommended_users,
    )


@main.route('/admin/profile')
def admin_profile():
    if current_user.is_authenticated and current_user.is_administrator():
        admin_user = current_user._get_current_object()
    else:
        admin_email = current_app.config.get('TALKTO_ADMIN')
        admin_user = User.query.filter_by(email=admin_email).first() if admin_email else None
        if admin_user is None:
            administrator_role = Role.query.filter_by(name='Administrator').first()
            if administrator_role is not None:
                admin_user = (
                    User.query
                    .filter_by(role_id=administrator_role.id)
                    .order_by(User.id.asc())
                    .first()
                )
        if admin_user is None:
            # Starter posts are platform content and do not require a personal
            # account to make the public Admin profile available.
            admin_user = SimpleNamespace(id=None, username='Admin')
    starter_posts = (
        Post.query
        .filter_by(is_starter=True, parent_id=None)
        .order_by(Post.timestamp.desc())
        .all()
    )
    return render_template(
        'user.html',
        user=admin_user,
        posts=starter_posts,
        activity=_profile_activity_payload(
            starter_posts,
            url_for('main.admin_profile'),
        ),
        return_to=None,
        recommend_profiles=False,
        recommended_users=[],
        force_admin_demo=True,
    )


@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    all_tags = Tag.library_names()
    if form.validate_on_submit():
        current_user.contact_email = User.normalize_email(form.contact_email.data) or None
        current_user.about_me = form.about_me.data
        current_user.funny_fact = form.funny_fact.data
        missing_tags = current_user.set_tags_from_string(form.tags.data, allow_create=False)
        current_user.set_profile_labels(form.label.data)
        if missing_tags:
            flash(
                "Unknown tags: {}. Only admins can create new tags.".format(', '.join(missing_tags))
            )
            return render_template('edit_profile.html', form=form, all_tags=all_tags, is_admin_edit=False)
        db.session.add(current_user)
        db.session.commit()
        flash('Your profile has been updated.')
        return redirect(url_for('main.settings', username=current_user.username))
    if request.method == 'GET':
        form.contact_email.data = current_user.contact_email
        form.about_me.data = current_user.about_me
        form.funny_fact.data = current_user.funny_fact
        form.label.data = current_user.profile_label_values
        form.tags.data = current_user.tag_string
    return render_template('edit_profile.html', form=form, all_tags=all_tags, is_admin_edit=False)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    all_tags = Tag.library_names()
    if form.validate_on_submit():
        user.email = form.email.data
        user.contact_email = User.normalize_email(form.contact_email.data) or None
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.about_me = form.about_me.data
        user.funny_fact = form.funny_fact.data
        user.set_tags_from_string(form.tags.data, allow_create=True)
        db.session.add(user)
        db.session.commit()
        flash('The profile has been updated.')
        return redirect(url_for('main.settings', username=user.username))

    if request.method == 'GET':
        form.email.data = user.email
        form.contact_email.data = user.contact_email
        form.username.data = user.username
        form.confirmed.data = user.confirmed
        form.role.data = user.role_id
        form.about_me.data = user.about_me
        form.funny_fact.data = user.funny_fact
        form.tags.data = user.tag_string
    return render_template('edit_profile.html', form=form, user=user, all_tags=all_tags, is_admin_edit=True)


@main.route('/tags')
def tag_search():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url, gate=1))
    all_tags = Tag.library_names()
    profile_label_choices = [("__none__", "No label")] + User.PROFILE_LABEL_CHOICES
    return render_template('tag_search.html', all_tags=all_tags, profile_label_choices=profile_label_choices, active_page='tag_search')

@main.route('/get-help-now')
def get_help_now():
    return render_template('get_help_now.html', active_page='get_help_now')

@main.route('/tags/search')
@login_required
def tag_search_api():
    query = request.args.get('q', '', type=str).strip()
    requested_profile_labels = {
        value.strip() for value in request.args.getlist('labels') if value and value.strip()
    }
    all_tags = Tag.library_names()
    all_tag_names = set(all_tags)
    selected_tags = []
    for value in request.args.getlist('tags'):
        normalized_value = value.strip().lower()
        if normalized_value in all_tag_names and normalized_value not in selected_tags:
            selected_tags.append(normalized_value)

    search_terms = []
    if query:
        search_terms.append(query)
    search_terms.extend(
        tag for tag in selected_tags
        if tag.lower() not in {term.lower() for term in search_terms}
    )

    matches_by_name = {}
    for search_term in search_terms:
        for candidate in match_tags(search_term, all_tags):
            existing = matches_by_name.get(candidate["name"])
            if existing is None:
                matches_by_name[candidate["name"]] = dict(candidate)
                continue
            existing["score"] = max(existing["score"], candidate["score"])
            existing["semantic"] = max(existing["semantic"], candidate["semantic"])
            existing["reasons"] = sorted(set(existing["reasons"] + candidate["reasons"]))

    matches = sorted(
        matches_by_name.values(),
        key=lambda item: (item["score"], item["name"]),
        reverse=True,
    )
    matched_tag_names = {m["name"] for m in matches}
    tag_map = {
        t.name: t for t in Tag.query.filter(Tag.name.in_([m["name"] for m in matches])).all()
    } if matches else {}

    for match in matches:
        tag = tag_map.get(match["name"])
        users = []
        if tag is not None:
            tag_users = [
                u for u in tag.users.order_by(User.username.asc()).all()
                if not current_user.is_authenticated or u.id != current_user.id
            ]
            for u in tag_users:
                user_profile_labels = set(u.profile_label_values)
                if requested_profile_labels:
                    allows_labelled_profile = bool(user_profile_labels & requested_profile_labels)
                    allows_unlabelled_profile = "__none__" in requested_profile_labels and not user_profile_labels
                    if not allows_labelled_profile and not allows_unlabelled_profile:
                        continue
                user_tag_names = sorted(t.name for t in u.tags)
                matching_tags = [name for name in user_tag_names if name in matched_tag_names]
                reason = (
                    "Matches on tags: " + ", ".join(matching_tags)
                    if matching_tags else
                    f"Matches on tag: {match['name']}"
                )
                users.append(
                    {
                        "id": u.id,
                        "username": u.username,
                        "profile_url": url_for('main.user', username=u.username),
                        "matching_tags": matching_tags,
                        "match_reason": reason,
                        "name": u.name or "",
                        "about_me": (u.about_me or "")[:180],
                        "funny_fact": (u.funny_fact or "")[:180],
                        "profile_labels": u.profile_label_texts,
                        "tags": user_tag_names[:8],
                        "avatar_url": u.gravatar(size=48),
                    }
                )
        match["users"] = users

    model_ready = get_model() is not None
    return jsonify({
        "query": query,
        "selected_tags": selected_tags,
        "matches": matches,
        "all_tags": all_tags,
        "semantic_model_ready": model_ready,
        "error": None if model_ready else "Semantic tag index is not available.",
    })


#für Testzwecke:
@main.route('/admin')
@login_required
@admin_required
def for_admins_only():
    return "For administrators!"


@main.route('/admin/demo-profile/<mode>', methods=['POST'])
@login_required
@admin_required
def set_admin_demo_profile(mode):
    if mode not in {'admin', 'personal'}:
        return ('', 404)
    set_admin_demo_mode(mode == 'admin')
    if mode == 'admin':
        flash('Admin profile is now active.')
    else:
        flash('Your personal profile is now visible to you.')
    if mode == 'admin':
        return redirect(url_for('main.admin_profile'))
    return redirect(url_for('main.user', username=current_user.username))


@main.route('/admin/starter-posts', methods=['GET', 'POST'])
@login_required
@admin_required
def starter_posts_admin():
    form = StarterPostForm()
    if form.validate_on_submit():
        starter_post = Post(
            body=form.body.data,
            author_id=None,
            post_type=form.post_type.data,
            is_starter=True,
        )
        db.session.add(starter_post)
        db.session.commit()
        flash('Starter post published as CommonRoom platform content.')
        return redirect(url_for('main.starter_posts_admin'))

    starter_posts = (
        Post.query
        .filter_by(is_starter=True, parent_id=None)
        .order_by(Post.id.desc())
        .all()
    )
    return render_template(
        'admin/starter_posts.html',
        form=form,
        starter_posts=starter_posts,
        editing_post=None,
        active_page=None,
    )


@main.route('/admin/starter-posts/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_starter_post_admin(post_id):
    starter_post = Post.query.filter_by(
        id=post_id,
        is_starter=True,
        parent_id=None,
    ).first_or_404()
    form = StarterPostForm(obj=starter_post)
    if form.validate_on_submit():
        starter_post.body = form.body.data
        starter_post.post_type = form.post_type.data
        starter_post.edited_at = datetime.now(timezone.utc)
        db.session.add(starter_post)
        db.session.commit()
        flash('Starter post updated.')
        return redirect(url_for('main.starter_posts_admin'))

    starter_posts = (
        Post.query
        .filter_by(is_starter=True, parent_id=None)
        .order_by(Post.id.desc())
        .all()
    )
    return render_template(
        'admin/starter_posts.html',
        form=form,
        starter_posts=starter_posts,
        editing_post=starter_post,
        active_page=None,
    )


@main.route('/analytics')
@login_required
@admin_required
def analytics():
    snapshot = _build_analytics_snapshot(
        request.args.get("range", "1w", type=str),
        request.args.get("segment", type=str),
    )
    return render_template('analytics.html', active_page=None, **snapshot)


@main.route('/analytics/export.csv')
@login_required
@admin_required
def analytics_export():
    dataset = request.args.get("dataset", "summary", type=str)
    if dataset not in ANALYTICS_EXPORT_DATASETS:
        dataset = "summary"
    snapshot = _build_analytics_snapshot(
        request.args.get("range", "1w", type=str),
        request.args.get("segment", type=str),
    )
    output = StringIO()
    writer = csv.writer(output)

    if dataset == "summary":
        writer.writerow(["category", "metric", "value", "period"])
        rows = [
            ("visits", "new tracked visits", snapshot["visit_timeline"]["total_visits"]),
            ("profiles", "profiles", snapshot["total_profiles"]),
            ("profiles", "with optional email", snapshot["profiles_with_contact_email"]),
            ("profiles", "without optional email", snapshot["profiles_without_contact_email"]),
            ("posts", "relate posts", snapshot["relate_post_count"]),
            ("posts", "question posts", snapshot["question_post_count"]),
            ("posts", "confession posts", snapshot["confession_post_count"]),
            ("posts", "posts with replies", snapshot["replied_post_count"]),
            ("posts", "replies", snapshot["total_replies"]),
            ("chats", "private chats", snapshot["total_conversations"]),
        ]
        for index, (category, metric, value) in enumerate(rows):
            period = snapshot["selected_range"] if index == 0 else "all-time"
            writer.writerow([category, metric, value, period])
    elif dataset == "pages":
        writer.writerow(["page", "visits", "average_seconds", "total_seconds", "public", "logged_in"])
        for item in snapshot["page_stats"]:
            writer.writerow([
                item["page_name"], item["visit_count"], item["avg_duration_seconds"],
                item["total_duration_seconds"], item["public_visits"], item["logged_in_visits"],
            ])
    elif dataset == "hours":
        writer.writerow(["local_hour", "visits", "timezone"])
        for item in snapshot["hour_distribution"]["points"]:
            writer.writerow([item["label"], item["count"], snapshot["hour_distribution"]["timezone"]])
    elif dataset == "journeys":
        writer.writerow(["view", "path_or_page", "sessions", "percent"])
        for item in snapshot["journey_stats"]["first_steps"]:
            writer.writerow(["first page after Home", item["page_name"], item["count"], item["percent"]])
        for item in snapshot["journey_stats"]["paths"]:
            writer.writerow(["first three steps", item["label"], item["count"], ""])
    elif dataset == "acquisition":
        writer.writerow(["view", "source", "sessions", "percent"])
        for item in snapshot["acquisition_stats"]["channels"]:
            writer.writerow(["channel", item["label"], item["count"], item["percent"]])
        for item in snapshot["acquisition_stats"]["sources"]:
            writer.writerow(["source and medium", item["label"], item["count"], ""])
        for item in snapshot["acquisition_stats"]["campaigns"]:
            writer.writerow(["campaign", item["label"], item["count"], ""])
    elif dataset == "funnel":
        writer.writerow(["trigger", "started", "completed", "abandoned"])
        for item in snapshot["auth_funnel_stats"]["actions"]:
            writer.writerow([
                item["label"], item["started"], item["completed"], item["abandoned"],
            ])
    else:
        writer.writerow(["page", "visits", "average_seconds", "total_seconds", "public", "logged_in"])
        for item in snapshot["previous_analytics"]["page_stats"]:
            writer.writerow([
                item["page_name"], item["visit_count"], item["avg_duration_seconds"],
                item["total_duration_seconds"], item["public_visits"], item["logged_in_visits"],
            ])

    export_period = "all-time" if dataset == "previous" else snapshot["selected_range"]
    segment_suffix = f"-{snapshot['selected_segment_key']}" if snapshot["selected_segment_key"] else ""
    filename = f"commonroom-analytics-{dataset}-{export_period}{segment_suffix}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@main.route('/moderator')
@login_required
@permission_required(Permission.MODERATE_COMMENTS)
def for_moderators_only():
    return "For comment moderators!"
