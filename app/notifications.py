from datetime import datetime, timezone

from flask import session, url_for

from . import db
from .models import (
    ChatRequest,
    Conversation,
    Message,
    Post,
    PostThreadSubscription,
    PostThreadVisit,
)


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


def _root_post(post):
    current = post
    visited_ids = set()
    while current.parent_id is not None and current.id not in visited_ids:
        visited_ids.add(current.id)
        current = current.parent
    return current


def unread_reply_threads_for_user(user):
    participation = Post.query.filter(Post.author_id == user.id).all()
    participated_root_ids = set()
    roots_by_id = {}
    participation_started_at = {}
    for post in participation:
        root = _root_post(post)
        participated_root_ids.add(root.id)
        roots_by_id[root.id] = root
        participated_at = _utc_aware(post.timestamp)
        previous = participation_started_at.get(root.id)
        if participated_at is not None and (previous is None or participated_at < previous):
            participation_started_at[root.id] = participated_at
    subscriptions = PostThreadSubscription.query.filter_by(user_id=user.id).all()
    for subscription in subscriptions:
        root = subscription.root_post
        if root is None:
            continue
        roots_by_id[root.id] = root
        subscribed_at = _utc_aware(subscription.created_at)
        previous = participation_started_at.get(root.id)
        if subscribed_at is not None and (previous is None or subscribed_at < previous):
            participation_started_at[root.id] = subscribed_at
    if not roots_by_id:
        return {}

    visits = {
        visit.root_post_id: _utc_aware(visit.last_visited_at)
        for visit in PostThreadVisit.query.filter(
            PostThreadVisit.user_id == user.id,
            PostThreadVisit.root_post_id.in_(roots_by_id),
        ).all()
    }

    relevant_replies = []
    frontier = set(roots_by_id)
    visited_post_ids = set(frontier)
    while frontier:
        children = Post.query.filter(Post.parent_id.in_(frontier)).all()
        frontier = set()
        for child in children:
            if child.id in visited_post_ids:
                continue
            visited_post_ids.add(child.id)
            frontier.add(child.id)
            relevant_replies.append(child)

    unread_by_root = {}
    for reply in relevant_replies:
        if reply.author_id == user.id:
            continue
        if reply.author is not None and user.has_block_relationship(reply.author):
            continue
        created_at = _utc_aware(reply.timestamp)
        if created_at is None:
            continue
        root = _root_post(reply)
        threshold = participation_started_at.get(root.id)
        last_visited_at = visits.get(root.id)
        if last_visited_at is not None and (threshold is None or last_visited_at > threshold):
            threshold = last_visited_at
        if threshold is not None and created_at <= threshold:
            continue

        author_name = reply.author.username if reply.author is not None else 'Admin'
        if root.author_id == user.id:
            text = f'{author_name} replied to your post'
        elif root.id not in participated_root_ids:
            text = f'{author_name} replied in a thread you follow'
        else:
            text = f'{author_name} replied to a post you also replied to'
        existing = unread_by_root.get(root.id)
        if existing is None or created_at > existing['timestamp']:
            unread_by_root[root.id] = {
                'kind': 'post_reply',
                'root_post': root,
                'reply': reply,
                'timestamp': created_at,
                'is_new': True,
                'text': text,
                'url': url_for('main.post_thread', post_id=root.id) + f'#post-{reply.id}',
            }
    return unread_by_root


def mark_post_thread_visited(user_id, root_post_id):
    visit = PostThreadVisit.query.filter_by(
        user_id=user_id,
        root_post_id=root_post_id,
    ).first()
    if visit is None:
        visit = PostThreadVisit(user_id=user_id, root_post_id=root_post_id)
        db.session.add(visit)
    visit.last_visited_at = datetime.now(timezone.utc)
    db.session.commit()


def build_notifications_for_user(user, limit=8):
    seen_at = notifications_seen_at()
    items = []

    items.extend(unread_reply_threads_for_user(user).values())

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
                    url_for("chat.detail", conversation_id=conversation.id)
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
                "url": url_for("chat.detail", conversation_id=conversation.id) + f"#message-{last_msg.id}",
            }
        )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    limited_items = items[:limit]
    return {
        "items": limited_items,
        "has_unseen": any(item["is_new"] for item in limited_items),
    }
