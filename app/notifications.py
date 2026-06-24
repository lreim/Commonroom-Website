from datetime import datetime, timezone

from flask import session, url_for

from .models import ChatRequest, Conversation, Message


SESSION_KEY = "notifications_last_seen_at"


def _parse_seen_at(raw_value):
    if not raw_value:
        return None
    try:
        value = datetime.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def notifications_seen_at():
    return _parse_seen_at(session.get(SESSION_KEY))


def mark_notifications_seen_now():
    session[SESSION_KEY] = datetime.now(timezone.utc).isoformat()
    session.modified = True


def build_notifications_for_user(user, limit=8):
    seen_at = notifications_seen_at()
    items = []

    pending_requests = ChatRequest.query.filter(
        ChatRequest.status == ChatRequest.STATUS_PENDING,
        ChatRequest.requested_id == user.id,
    ).order_by(ChatRequest.created_at.desc()).all()
    for chat_request in pending_requests:
        created_at = _utc_aware(chat_request.created_at)
        items.append(
            {
                "kind": "incoming_request",
                "timestamp": created_at,
                "is_new": seen_at is None or created_at > seen_at,
                "text": f"New chat request from {chat_request.requester.username}",
                "url": url_for("chat.index") + "#requested-chats",
            }
        )

    responded_requests = ChatRequest.query.filter(
        ChatRequest.requester_id == user.id,
        ChatRequest.status.in_([ChatRequest.STATUS_ACCEPTED, ChatRequest.STATUS_REJECTED]),
        ChatRequest.responded_at.isnot(None),
    ).order_by(ChatRequest.responded_at.desc()).all()
    for chat_request in responded_requests:
        responded_at = _utc_aware(chat_request.responded_at)
        if responded_at is None:
            continue
        response_word = "accepted" if chat_request.status == ChatRequest.STATUS_ACCEPTED else "rejected"
        conversation = Conversation.query.filter(
            (
                ((Conversation.user_a_id == chat_request.requester_id) & (Conversation.user_b_id == chat_request.requested_id)) |
                ((Conversation.user_a_id == chat_request.requested_id) & (Conversation.user_b_id == chat_request.requester_id))
            )
        ).first()
        items.append(
            {
                "kind": "request_response",
                "timestamp": responded_at,
                "is_new": seen_at is None or responded_at > seen_at,
                "text": f"{chat_request.requested.username} {response_word} your chat request",
                "url": (
                    url_for("chat.index") + f"#chat-conversation-{conversation.id}"
                    if chat_request.status == ChatRequest.STATUS_ACCEPTED and conversation is not None
                    else (
                        url_for("chat.index") + "#your-chats"
                        if chat_request.status == ChatRequest.STATUS_ACCEPTED
                        else url_for("chat.index") + "#requested-chats"
                    )
                ),
            }
        )

    conversations = Conversation.query.filter(
        (Conversation.user_a_id == user.id) | (Conversation.user_b_id == user.id)
    ).all()
    for conversation in conversations:
        last_msg = conversation.messages.order_by(Message.created_at.desc()).first()
        if last_msg is None or last_msg.author_id == user.id:
            continue
        other = conversation.other_user(user.id)
        if user.has_block_relationship(other):
            continue
        created_at = _utc_aware(last_msg.created_at)
        items.append(
            {
                "kind": "message",
                "timestamp": created_at,
                "is_new": seen_at is None or created_at > seen_at,
                "text": f"New message from {other.username}",
                "url": url_for("chat.index") + f"#chat-conversation-{conversation.id}",
            }
        )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    limited_items = items[:limit]
    return {
        "items": limited_items,
        "has_unseen": any(item["is_new"] for item in limited_items),
    }
