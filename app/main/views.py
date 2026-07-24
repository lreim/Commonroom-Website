from datetime import datetime, timezone, timedelta
from math import sqrt
from urllib.parse import urlparse
from uuid import uuid4
from sqlalchemy import func
from flask import render_template, session, redirect, url_for, current_app, request, flash, jsonify
from . import main
from .forms import PostForm, EditProfileForm, EditProfileAdminForm, FeedbackForm
from .. import db
from ..models import User, Post, Role, Tag, Conversation, PageVisit
from ..tag_matching import match_tags, get_model
from flask_login import login_required, current_user
from app.decorators import admin_required, permission_required
from ..models import Permission
from ..email import send_email

#ATTENTION: with blueprint use main. iinstead of app. 

TRACKED_NAVBAR_PAGES = {
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


def _build_visit_timeline(range_key):
    now = datetime.now(timezone.utc)
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
        PageVisit.query
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
                "label": bucket_start.strftime(label_format),
                "count": counts_by_index[index],
            }
        )

    return {
        "range_key": range_key,
        "points": points,
        "max_count": max_count,
        "total_visits": sum(point["count"] for point in points),
    }

#routes (view functions sind die index() etc.) for every page I have: @login_required before route to make it safe
#für externe Inhalte, mails, magic links nutze external=True
#The methods argument added to the app.route decorator tells Flask to register the view
#function as a handler for GET and POST requests in the URL map. When methods is not
#given, the view function is registered to handle GET requests only.
@main.route('/')
def index():
    return render_template('index.html', active_page='index', current_time=datetime.now(timezone.utc))

@main.route('/settings')
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
def track_page_visit():
    if not _analytics_request_has_same_origin():
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    page_key = (payload.get("page_key") or "").strip()
    path = (payload.get("path") or request.path or "").strip()
    duration_ms = payload.get("duration_ms", 0)
    visit_token = (payload.get("visit_token") or "").strip()
    device_type = (payload.get("device_type") or "desktop").strip().lower()

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

    normalized_path = path[:255] or "/"
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
        user_id=current_user.id if current_user.is_authenticated else None,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
    )
    db.session.add(visit)
    db.session.commit()
    return ("", 204)

@main.route('/post', methods=['GET', 'POST'])
@login_required
def post():
    form = PostForm()
    reply_to_id = request.form.get('reply_to_id', type=int)
    if form.validate_on_submit():
        parent_post = None
        if reply_to_id:
            parent_post = Post.query.get_or_404(reply_to_id)
            if parent_post.parent is not None:
                parent_post = parent_post.parent
        post = Post(
            body=form.body.data,
            author=current_user._get_current_object(),
            parent=parent_post,
        )
        db.session.add(post)
        db.session.commit()
        if parent_post is not None:
            return redirect(url_for('main.post_thread', post_id=parent_post.id))
        return redirect(url_for('main.post'))

    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
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

    sort_by = request.args.get('sort', 'most_recent', type=str)
    page = request.args.get('page', 1, type=int)
    post_query = Post.query.filter(Post.parent_id.is_(None))
    if matched_topics:
        post_query = post_query.join(User, Post.author).join(User.tags).filter(Tag.name.in_(matched_topics)).distinct()

    if sort_by == 'most_recent':
        post_query = post_query.order_by(Post.id.desc(), Post.timestamp.desc())
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
    elif sort_by == 'oldest_first':
        post_query = post_query.order_by(Post.id.asc(), Post.timestamp.asc())
    else:
        sort_by = 'most_recent'
        post_query = post_query.order_by(Post.id.desc(), Post.timestamp.desc())

    pagination = post_query.paginate(
        page=page,
        per_page=current_app.config.get('TALKTO_POSTS_PER_PAGE', 20),
        error_out=False
    )
    posts = pagination.items
    return render_template(
        'post.html',
        form=form,
        posts=posts,
        pagination=pagination,
        all_tags=all_tags,
        selected_topics=', '.join(selected_topics),
        matched_topics=matched_topics,
        sort_by=sort_by,
        active_page='post',
    )


@main.route('/post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def post_thread(post_id):
    root_post = Post.query.get_or_404(post_id)
    if root_post.parent is not None:
        return redirect(url_for('main.post_thread', post_id=root_post.parent_id))

    form = PostForm()
    reply_to_id = request.form.get('reply_to_id', type=int)
    if current_user.can(Permission.WRITE_ARTICLES) and form.validate_on_submit():
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
            author=current_user._get_current_object(),
            parent=parent_post,
        )
        db.session.add(reply)
        db.session.commit()
        return redirect(url_for('main.post_thread', post_id=root_post.id))

    return render_template(
        'post_thread.html',
        post=root_post,
        form=form,
    )

@main.route('/user/<username>')
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = user.posts.order_by(Post.timestamp.desc()).all()
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
        recommend_profiles=recommend_profiles,
        recommended_users=recommended_users,
    )


@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
    if form.validate_on_submit():
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
    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
    if form.validate_on_submit():
        user.email = form.email.data
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
        form.username.data = user.username
        form.confirmed.data = user.confirmed
        form.role.data = user.role_id
        form.about_me.data = user.about_me
        form.funny_fact.data = user.funny_fact
        form.tags.data = user.tag_string
    return render_template('edit_profile.html', form=form, user=user, all_tags=all_tags, is_admin_edit=True)


@main.route('/tags')
@login_required
def tag_search():
    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
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
    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
    matches = match_tags(query, all_tags)
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
            ][:6]
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
                        "profile_labels": u.profile_label_texts,
                        "tags": user_tag_names[:8],
                        "avatar_url": u.gravatar(size=48),
                    }
                )
        match["users"] = users

    model_ready = get_model() is not None
    return jsonify({
        "query": query,
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


@main.route('/analytics')
@login_required
@admin_required
def analytics():
    selected_range = request.args.get("range", "1w", type=str)
    page_rows = (
        db.session.query(
            PageVisit.page_key,
            func.count(PageVisit.id).label("visit_count"),
            func.avg(PageVisit.duration_seconds).label("avg_duration_seconds"),
            func.sum(PageVisit.duration_seconds).label("total_duration_seconds"),
        )
        .group_by(PageVisit.page_key)
        .order_by(func.count(PageVisit.id).desc())
        .all()
    )

    page_stats = []
    for row in page_rows:
        page_stats.append(
            {
                "page_key": row.page_key,
                "page_name": TRACKED_NAVBAR_PAGES.get(row.page_key, row.page_key),
                "visit_count": int(row.visit_count or 0),
                "avg_duration_seconds": round(float(row.avg_duration_seconds or 0), 1),
                "total_duration_seconds": int(row.total_duration_seconds or 0),
            }
        )

    device_rows = (
        db.session.query(
            PageVisit.device_type,
            func.count(PageVisit.id).label("visit_count"),
        )
        .group_by(PageVisit.device_type)
        .all()
    )
    device_stats = {"mobile": 0, "desktop": 0}
    for row in device_rows:
        if row.device_type in device_stats:
            device_stats[row.device_type] = int(row.visit_count or 0)

    root_post_count = Post.query.filter(Post.parent_id.is_(None)).count()
    reply_count = Post.query.filter(Post.parent_id.isnot(None)).count()
    conversation_count = Conversation.query.count()
    chat_stats = _compute_chat_count_stats()
    visit_timeline = _build_visit_timeline(selected_range)

    return render_template(
        'analytics.html',
        active_page=None,
        page_stats=page_stats,
        device_stats=device_stats,
        visit_timeline=visit_timeline,
        selected_range=visit_timeline["range_key"],
        tracked_page_count=len(page_stats),
        total_root_posts=root_post_count,
        total_replies=reply_count,
        total_posts_including_replies=root_post_count + reply_count,
        total_conversations=conversation_count,
        max_chats_per_user=chat_stats["max_chats_per_user"],
        chat_count_std_dev=round(chat_stats["chat_count_std_dev"], 2),
        tracked_user_count=chat_stats["user_count"],
    )

@main.route('/moderator')
@login_required
@permission_required(Permission.MODERATE_COMMENTS)
def for_moderators_only():
    return "For comment moderators!"
