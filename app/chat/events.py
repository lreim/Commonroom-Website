from flask_socketio import emit, join_room
from flask_login import current_user

from .. import socketio, db
from ..models import Conversation, Message


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
            "body": msg.body,
            "created_at": msg.created_at.isoformat(),
        },
        to=_room_name(conversation_id),
    )
