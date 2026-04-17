from flask import render_template, redirect, url_for, request, abort
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
        items.append({"conversation": c, "other": other, "last_msg": last_msg})

    q = request.args.get("q", "", type=str).strip()
    users = []
    if q:
        users = User.query.filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        ).order_by(User.username.asc()).limit(25).all()
    return render_template("chat/list.html", items=items, users=users, q=q)


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
