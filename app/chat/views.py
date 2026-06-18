from flask import render_template, redirect, url_for, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from . import chat
from .. import db
from ..models import User, Conversation, Message


def _pair_ids(user1_id, user2_id):
    return (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)


@chat.route("/")
@login_required
def index():     #Zeigt Übersicht aller Chats, in denen current_user involviert ist 
    conversations = Conversation.query.filter(
        (Conversation.user_a_id == current_user.id) | (Conversation.user_b_id == current_user.id)
    ).order_by(Conversation.created_at.desc()).all()

    items = []
    for c in conversations:
        other = c.other_user(current_user.id)
        last_msg = c.messages.order_by(Message.created_at.desc()).first()
        last_activity = last_msg.created_at if last_msg else c.created_at
        message_count = c.messages.count()
        current_tags = {t.name for t in current_user.tags}
        other_tags = {t.name for t in other.tags}
        match_count = len(current_tags & other_tags)
        matching_tags = sorted(current_tags & other_tags)
        items.append({"conversation": c, "other": other, "last_msg": last_msg, "last_activity": last_activity, "message_count": message_count, "match_count": match_count, "matching_tags": matching_tags})  #alles in items in dictinary packen
    
    #baue den Filter ein, je nachdem, was in der URL steht
    sort_by = request.args.get("sort", "most_recent")
    if sort_by == "most_active":
        items.sort(key=lambda x: x["message_count"], reverse=True)
    elif sort_by == "most_matching_tags":
        items.sort(key=lambda x: x["match_count"], reverse=True)
    else:
        items.sort(key=lambda x: x["last_activity"], reverse=True)

    q = request.args.get("q", "", type=str).strip()    #q ist der Suchtext 
    users = []
    if q:
        users = User.query.filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))  #Suchtext darf irgendwo im String stehen, 
        ).order_by(User.username.asc()).limit(25).all()     #auf 25 Treffer begrenzen
    return render_template("chat/list.html", items=items, users=users, q=q, sort_by=sort_by)


@chat.route("/search_users")
@login_required
def search_users():
    q = request.args.get("q", "", type=str).strip()
    users = []
    if q:
        users = User.query.filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        ).order_by(User.username.asc()).limit(25).all()

    return jsonify({
        "query": q,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "avatar_url": u.gravatar(size=56),
                "profile_url": url_for("main.user", username=u.username),
                "start_url": url_for("chat.start", user_id=u.id),
            }
            for u in users
        ],
    })


@chat.route("/start/<int:user_id>", methods=["POST"])
@login_required
def start(user_id):
    if user_id == current_user.id:
        abort(400)

    other = User.query.get_or_404(user_id)
    a_id, b_id = _pair_ids(current_user.id, other.id)

    conversation = Conversation.query.filter_by(user_a_id=a_id, user_b_id=b_id).first()
    if conversation is None:
        conversation = Conversation(user_a_id=a_id, user_b_id=b_id)
        db.session.add(conversation)
        db.session.commit()

    return redirect(url_for("chat.detail", conversation_id=conversation.id))


@chat.route("/<int:conversation_id>")
@login_required
def detail(conversation_id):    #lädt Konversation 
    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.has_user(current_user.id):
        abort(403)

    page = request.args.get("page", 1, type=int)
    pagination = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    messages = list(reversed(pagination.items))
    other = conversation.other_user(current_user.id)

    return render_template(
        "chat/detail.html",
        conversation=conversation,
        other=other,
        messages=messages,
        pagination=pagination,
    )
