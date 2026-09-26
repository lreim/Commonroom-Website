from flask_socketio import emit, join_room
from flask_login import current_user
from flask import url_for
from datetime import datetime, timezone

from .. import socketio, db
from ..models import Conversation, Message

CHAT_MESSAGE_MAX_LENGTH = 2000


def _room_name(conversation_id):
    return f"conversation_{conversation_id}"


@socketio.on("join_conversation")
def join_conversation(data):
    if not current_user.is_authenticated:
        emit("chat_error", {"message": "Not authenticated"})
        return

    conversation_id = int(data.get("conversation_id"))
    conversation = Conversation.query.get(conversation_id)
    if conversation is None or not conversation.has_user(current_user.id):
        emit("chat_error", {"message": "No access"})
        return

    join_room(_room_name(conversation_id))


@socketio.on("send_message")
def send_message(data):
    if not current_user.is_authenticated:
        emit("chat_error", {"message": "Not authenticated"})
        return

    conversation_id = int(data.get("conversation_id"))
    body = (data.get("body") or "").strip()
    if not body:
        emit("chat_error", {"message": "Empty message"})
        return
    if len(body) > CHAT_MESSAGE_MAX_LENGTH:
        emit("chat_error", {"message": f"Message too long. Please keep it under {CHAT_MESSAGE_MAX_LENGTH} characters."})
        return

    conversation = Conversation.query.get(conversation_id)
    if conversation is None or not conversation.has_user(current_user.id):
        emit("chat_error", {"message": "No access"})
        return

    other = conversation.other_user(current_user.id)
    if current_user.has_block_relationship(other):
        emit("chat_error", {"message": "You cannot send messages in this chat."})
        return

    msg = Message(conversation_id=conversation_id, author_id=current_user.id, body=body)
    db.session.add(msg)
    db.session.commit()

    emit(
        "new_message",
        {
            "id": msg.id,
            "conversation_id": conversation_id,
            "author_id": msg.author_id,
            "author_username": current_user.username,
            "author_profile_url": url_for("main.user", username=current_user.username),
            "body": msg.body,
            "created_at": msg.created_at.isoformat(),
        },
        to=_room_name(conversation_id),
    )


@socketio.on("edit_message")
def edit_message(data):
    if not current_user.is_authenticated:
        emit("chat_error", {"message": "Not authenticated"})
        return

    message_id = data.get("message_id")
    body = (data.get("body") or "").strip()
    if not body:
        emit("chat_error", {"message": "Empty message"})
        return
    if len(body) > CHAT_MESSAGE_MAX_LENGTH:
        emit("chat_error", {"message": f"Message too long. Please keep it under {CHAT_MESSAGE_MAX_LENGTH} characters."})
        return

    msg = Message.query.get(message_id)
    if msg is None or msg.author_id != current_user.id:
        emit("chat_error", {"message": "You can only edit your own messages."})
        return
    conversation = msg.conversation
    if current_user.has_block_relationship(conversation.other_user(current_user.id)):
        emit("chat_error", {"message": "You cannot edit messages in this chat."})
        return

    msg.body = body
    msg.edited_at = datetime.now(timezone.utc)
    db.session.commit()
    emit("message_edited", {
        "id": msg.id,
        "conversation_id": conversation.id,
        "body": msg.body,
        "edited_at": msg.edited_at.isoformat(),
    }, to=_room_name(conversation.id))
