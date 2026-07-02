from datetime import datetime, timezone 
from flask import render_template, session, redirect, url_for, current_app, request, flash, jsonify
from . import main
from .forms import PostForm, EditProfileForm, EditProfileAdminForm
from .. import db
from ..models import User, Post, Role, Tag
from ..tag_matching import match_tags, get_model
from flask_login import login_required, current_user
from app.decorators import admin_required, permission_required
from ..models import Permission

#ATTENTION: with blueprint use main. iinstead of app. 

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

@main.route('/post', methods=['GET', 'POST'])
@login_required
def post():
    form = PostForm()
    reply_to_id = request.form.get('reply_to_id', type=int)
    if current_user.can(Permission.WRITE_ARTICLES) and form.validate_on_submit():
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
        post_query = post_query.order_by(Post.timestamp.desc())
    else:
        sort_by = 'most_recent'
        post_query = post_query.order_by(Post.timestamp.desc())

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
    return render_template('tag_search.html', all_tags=all_tags, profile_label_choices=profile_label_choices)

@main.route('/get-help-now')
def get_help_now():
    return render_template('get_help_now.html')

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
        "error": None if model_ready else "SentenceTransformer model could not be loaded.",
    })


#für Testzwecke:
@main.route('/admin')
@login_required
@admin_required
def for_admins_only():
    return "For administrators!"

@main.route('/moderator')
@login_required
@permission_required(Permission.MODERATE_COMMENTS)
def for_moderators_only():
    return "For comment moderators!"
