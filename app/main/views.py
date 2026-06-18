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
@login_required
def onboarding():
    return render_template('onboarding.html', active_page='onboarding')

@main.route('/rules')
@login_required
def rules():
    return render_template('rules.html', active_page='rules')

@main.route('/post', methods=['GET', 'POST'])
@login_required
def post():
    form = PostForm()
    if current_user.can(Permission.WRITE_ARTICLES) and form.validate_on_submit():
        post = Post(body=form.body.data, author=current_user._get_current_object())
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('main.post'))

    page = request.args.get('page', 1, type=int)
    pagination = Post.query.order_by(Post.timestamp.desc()).paginate(
        page=page,
        per_page=current_app.config.get('TALKTO_POSTS_PER_PAGE', 20),
        error_out=False
    )
    posts = pagination.items
    return render_template('post.html', form=form, posts=posts, pagination=pagination)

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
        missing_tags = current_user.set_tags_from_string(form.tags.data, allow_create=False)
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
        form.tags.data = user.tag_string
    return render_template('edit_profile.html', form=form, user=user, all_tags=all_tags, is_admin_edit=True)


@main.route('/tags')
def tag_search():
    all_tags = [t.name for t in Tag.query.order_by(Tag.name.asc()).all()]
    return render_template('tag_search.html', all_tags=all_tags)


@main.route('/tags/search')
def tag_search_api():
    query = request.args.get('q', '', type=str).strip()
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
                user_tag_names = sorted(t.name for t in u.tags)
                matching_tags = [name for name in user_tag_names if name in matched_tag_names]
                reason = (
                    "Matches on tags: " + ", ".join(matching_tags)
                    if matching_tags else
                    f"Matches on tag: {match['name']}"
                )
                users.append(
                    {
                        "username": u.username,
                        "profile_url": url_for('main.user', username=u.username),
                        "matching_tags": matching_tags,
                        "match_reason": reason,
                        "name": u.name or "",
                        "location": u.location or "",
                        "about_me": (u.about_me or "")[:180],
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
