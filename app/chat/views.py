from datetime import datetime, timezone
from types import SimpleNamespace

from flask import render_template, redirect, url_for, request, abort, jsonify, flash
from flask_login import login_required, current_user
from sqlalchemy import or_

from . import chat
from .. import db
from ..email import send_email
from ..models import User, Conversation, Message, UserBlock, ChatRequest
from ..notifications import mark_notifications_seen_now
from ..security import is_safe_local_redirect_target


def _pair_ids(user1_id, user2_id):
    return (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)


def _safe_next_url(default_endpoint="chat.index", anchor=None):
    next_url = request.form.get("next") or request.args.get("next")
    if is_safe_local_redirect_target(next_url):
        return next_url
    target = url_for(default_endpoint)
    if anchor:
        target = f"{target}#{anchor}"
    return target


def _blocked_message(current_user, other_user):
    if current_user.has_blocked(other_user):
        return "You blocked this user. Unblock them to continue chatting."
    if current_user.is_blocked_by(other_user):
        return "You cannot chat with this user."
    return "Chat is unavailable."


def _pending_request_between(user_a_id, user_b_id):
    return ChatRequest.query.filter(
        ChatRequest.status == ChatRequest.STATUS_PENDING,
        (
            ((ChatRequest.requester_id == user_a_id) & (ChatRequest.requested_id == user_b_id)) |
            ((ChatRequest.requester_id == user_b_id) & (ChatRequest.requested_id == user_a_id))
        ),
    ).first()


def _create_or_get_conversation(user_a_id, user_b_id):
    a_id, b_id = _pair_ids(user_a_id, user_b_id)
    conversation = Conversation.query.filter_by(user_a_id=a_id, user_b_id=b_id).first()
    if conversation is None:
        conversation = Conversation(user_a_id=a_id, user_b_id=b_id)
        db.session.add(conversation)
        db.session.commit()
    return conversation


def _send_chat_request_email(chat_request, message_stream=None):
    accept_token = chat_request.generate_response_token("accept")
    reject_token = chat_request.generate_response_token("reject")
    send_email(
        chat_request.requested.email,
        "New chat request",
        "chat/email/request_chat",
        message_stream=message_stream or current_app.config.get('POSTMARK_MESSAGE_STREAM_CHAT_REQUEST'),
        chat_request=chat_request,
        requester=chat_request.requester,
        requested=chat_request.requested,
        accept_url=url_for("chat.accept_request", token=accept_token, _external=True),
        reject_url=url_for("chat.reject_request", token=reject_token, _external=True),
    )


def _render_request_response_page(token, action):
    chat_request = ChatRequest.resolve_response_token(token, expected_action=action)
    if chat_request is None:
        return render_template("chat/request_response.html", status="invalid", action=action)

    if chat_request.status != ChatRequest.STATUS_PENDING:
        return render_template(
            "chat/request_response.html",
            status="already_processed",
            action=action,
            chat_request=chat_request,
        )

    return render_template(
        "chat/request_response.html",
        status="confirm",
        action=action,
        token=token,
        chat_request=chat_request,
    )


def _serialize_chat_candidate(user):
    pending_request = _pending_request_between(current_user.id, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "avatar_url": user.gravatar(size=56),
        "profile_url": url_for("main.user", username=user.username),
        "has_pending_request": pending_request is not None,
        "pending_status_url": url_for("chat.pending_request_notice", user_id=user.id),
    }


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

    active_items = []
    blocked_items = []
    for item in items:
        if current_user.has_block_relationship(item["other"]):
            blocked_items.append(item)
        else:
            active_items.append(item)

    requested_items = []
    pending_requests = ChatRequest.query.filter(
        ChatRequest.status == ChatRequest.STATUS_PENDING,
        (
            (ChatRequest.requester_id == current_user.id) |
            (ChatRequest.requested_id == current_user.id)
        ),
    ).order_by(ChatRequest.created_at.desc()).all()
    for chat_request in pending_requests:
        other = chat_request.other_user(current_user.id)
        requested_items.append(
            {
                "request": chat_request,
                "other": other,
                "direction": chat_request.direction_for(current_user.id),
            }
        )

    q = request.args.get("q", "", type=str).strip()    #q ist der Suchtext 
    users = []
    if q:
        candidate_users = User.query.filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))  #Suchtext darf irgendwo im String stehen, 
        ).order_by(User.username.asc()).limit(25).all()     #auf 25 Treffer begrenzen
        users = [
            _serialize_chat_candidate(u)
            for u in candidate_users
            if not current_user.has_block_relationship(u)
        ]
    return render_template(
        "chat/list.html",
        items=active_items,
        blocked_items=blocked_items,
        requested_items=requested_items,
        users=users,
        q=q,
        sort_by=sort_by,
        active_page="chat_index",
    )


@chat.route("/search_users")
@login_required
def search_users():
    q = request.args.get("q", "", type=str).strip()
    users = []
    if q:
        candidate_users = User.query.filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        ).order_by(User.username.asc()).limit(25).all()
        users = [
            _serialize_chat_candidate(u)
            for u in candidate_users
            if not current_user.has_block_relationship(u)
        ]

    return jsonify({
        "query": q,
        "users": users,
    })


@chat.route("/notifications/mark-seen", methods=["POST"])
@login_required
def mark_notifications_seen():
    mark_notifications_seen_now()
    return jsonify({"ok": True})


@chat.route("/start/<int:user_id>", methods=["POST"])
@login_required
def start(user_id):
    flash("Use the chat request form to start a new conversation.")
    return redirect(url_for("chat.index"))


@chat.route("/request/pending/<int:user_id>")
@login_required
def pending_request_notice(user_id):
    other = User.query.get_or_404(user_id)
    if _pending_request_between(current_user.id, other.id) is not None:
        flash("There is already a pending chat request between you and this user.")
    return redirect(_safe_next_url())


@chat.route("/request", methods=["POST"])
@login_required
def request_chat():
    requested_id = request.form.get("requested_user_id", type=int)
    body = (request.form.get("message") or "").strip()
    next_url = _safe_next_url()

    if not requested_id:
        abort(400)
    if requested_id == current_user.id:
        abort(400)
    if not body:
        flash("Please write a short request message first.")
        return redirect(next_url)

    other = User.query.get_or_404(requested_id)
    if current_user.has_block_relationship(other):
        abort(403)

    existing_conversation = Conversation.query.filter(
        ((Conversation.user_a_id == current_user.id) & (Conversation.user_b_id == other.id)) |
        ((Conversation.user_a_id == other.id) & (Conversation.user_b_id == current_user.id))
    ).first()
    if existing_conversation is not None:
        flash("You already have an active chat with this user.")
        return redirect(url_for("chat.detail", conversation_id=existing_conversation.id))

    pending_request = _pending_request_between(current_user.id, other.id)
    if pending_request is not None:
        flash("There is already a pending chat request between you and this user.")
        return redirect(next_url)

    chat_request = ChatRequest(
        requester_id=current_user.id,
        requested_id=other.id,
        message=body,
        status=ChatRequest.STATUS_PENDING,
    )
    db.session.add(chat_request)
    db.session.commit()

    _send_chat_request_email(chat_request)

    flash("Your chat request has been sent by email.")
    return redirect(next_url)


@chat.route("/request/<int:request_id>/withdraw", methods=["POST"])
@login_required
def withdraw_request(request_id):
    chat_request = ChatRequest.query.get_or_404(request_id)
    if chat_request.requester_id != current_user.id:
        abort(403)
    if chat_request.status != ChatRequest.STATUS_PENDING:
        flash("This chat request can no longer be withdrawn.")
        return redirect(url_for("chat.index"))

    db.session.delete(chat_request)
    db.session.commit()
    flash("Your chat request has been withdrawn.")
    return redirect(url_for("chat.index") + "#requested-chats")


@chat.route("/request/<int:request_id>/resend", methods=["POST"])
@login_required
def resend_request(request_id):
    chat_request = ChatRequest.query.get_or_404(request_id)
    if chat_request.requester_id != current_user.id:
        abort(403)
    if chat_request.status != ChatRequest.STATUS_PENDING:
        flash("This chat request can no longer be resent.")
        return redirect(url_for("chat.index"))
    if current_user.has_block_relationship(chat_request.requested):
        abort(403)

    chat_request.created_at = datetime.now(timezone.utc)
    db.session.add(chat_request)
    db.session.commit()
    _send_chat_request_email(
        chat_request,
        message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_CHAT_REQUEST_RESEND'),
    )

    flash("Your chat request has been sent again by email.")
    return redirect(url_for("chat.index") + "#requested-chats")


@chat.route("/<int:conversation_id>")
@login_required
def detail(conversation_id):    #lädt Konversation 
    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.has_user(current_user.id):
        abort(403)

    page = request.args.get("page", 1, type=int)
    per_page = 20
    visible_message_count = max(page, 1) * per_page
    total_message_count = Message.query.filter_by(conversation_id=conversation.id).count()
    message_items = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.created_at.desc()).limit(
        visible_message_count
    ).all()
    messages = list(reversed(message_items))
    pagination = SimpleNamespace(
        has_next=total_message_count > visible_message_count,
        next_num=page + 1,
    )
    other = conversation.other_user(current_user.id)
    is_blocked = current_user.has_block_relationship(other)
    blocked_message = _blocked_message(current_user, other) if is_blocked else None

    return render_template(
        "chat/detail.html",
        conversation=conversation,
        other=other,
        messages=messages,
        pagination=pagination,
        is_blocked=is_blocked,
        blocked_message=blocked_message,
    )


@chat.route("/request/accept/<token>", methods=["GET", "POST"])
def accept_request(token):
    if request.method == "GET":
        return _render_request_response_page(token, "accept")

    chat_request = ChatRequest.resolve_response_token(token, expected_action="accept")
    if chat_request is None:
        return render_template("chat/request_response.html", status="invalid", action="accept")
    if chat_request.status != ChatRequest.STATUS_PENDING:
        return render_template(
            "chat/request_response.html",
            status="already_processed",
            action="accept",
            chat_request=chat_request,
        )
    if chat_request.requester.has_block_relationship(chat_request.requested):
        chat_request.status = ChatRequest.STATUS_REJECTED
        chat_request.responded_at = datetime.now(timezone.utc)
        db.session.add(chat_request)
        db.session.commit()
        return render_template(
            "chat/request_response.html",
            status="blocked",
            action="accept",
            chat_request=chat_request,
        )

    conversation = _create_or_get_conversation(chat_request.requester_id, chat_request.requested_id)
    chat_request.status = ChatRequest.STATUS_ACCEPTED
    chat_request.responded_at = datetime.now(timezone.utc)
    db.session.add(chat_request)
    db.session.commit()
    return render_template(
        "chat/request_response.html",
        status="accepted",
        action="accept",
        chat_request=chat_request,
        conversation=conversation,
    )


@chat.route("/request/reject/<token>", methods=["GET", "POST"])
def reject_request(token):
    if request.method == "GET":
        return _render_request_response_page(token, "reject")

    chat_request = ChatRequest.resolve_response_token(token, expected_action="reject")
    if chat_request is None:
        return render_template("chat/request_response.html", status="invalid", action="reject")
    if chat_request.status != ChatRequest.STATUS_PENDING:
        return render_template(
            "chat/request_response.html",
            status="already_processed",
            action="reject",
            chat_request=chat_request,
        )
    chat_request.status = ChatRequest.STATUS_REJECTED
    chat_request.responded_at = datetime.now(timezone.utc)
    db.session.add(chat_request)
    db.session.commit()
    return render_template(
        "chat/request_response.html",
        status="rejected",
        action="reject",
        chat_request=chat_request,
    )


@chat.route("/block/<int:user_id>", methods=["POST"])
@login_required
def block_user(user_id):
    if user_id == current_user.id:
        abort(400)

    other = User.query.get_or_404(user_id)
    if not current_user.has_blocked(other):
        db.session.add(UserBlock(blocker_id=current_user.id, blocked_id=other.id))
        db.session.commit()

    conversation = Conversation.query.filter(
        ((Conversation.user_a_id == current_user.id) & (Conversation.user_b_id == other.id)) |
        ((Conversation.user_a_id == other.id) & (Conversation.user_b_id == current_user.id))
    ).first()
    if conversation is not None:
        return redirect(url_for("chat.detail", conversation_id=conversation.id))
    return redirect(url_for("chat.index"))


@chat.route("/unblock/<int:user_id>", methods=["POST"])
@login_required
def unblock_user(user_id):
    if user_id == current_user.id:
        abort(400)

    other = User.query.get_or_404(user_id)
    block = UserBlock.query.filter_by(blocker_id=current_user.id, blocked_id=other.id).first()
    if block is not None:
        db.session.delete(block)
        db.session.commit()

    conversation = Conversation.query.filter(
        ((Conversation.user_a_id == current_user.id) & (Conversation.user_b_id == other.id)) |
        ((Conversation.user_a_id == other.id) & (Conversation.user_b_id == current_user.id))
    ).first()
    if conversation is not None:
        return redirect(url_for("chat.detail", conversation_id=conversation.id))
    return redirect(url_for("chat.index"))
