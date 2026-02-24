from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models.communication import Message, MessageRead, Thread, ThreadMember


def create_thread(tenant_id: int, title: str, thread_type: str, created_by: int, member_ids: list[int]):
    thread = Thread(
        tenant_id=tenant_id,
        title=title,
        thread_type=thread_type,
        created_by=created_by,
    )
    db.session.add(thread)
    db.session.flush()

    member_set = set(member_ids)
    member_set.add(created_by)
    for user_id in member_set:
        db.session.add(ThreadMember(tenant_id=tenant_id, thread_id=thread.id, user_id=user_id))

    db.session.commit()
    return thread


def post_message(tenant_id: int, thread_id: int, sender_id: int, body: str):
    message = Message(
        tenant_id=tenant_id,
        thread_id=thread_id,
        sender_id=sender_id,
        body=body,
    )
    db.session.add(message)
    db.session.commit()
    return message


def mark_read(tenant_id: int, message_id: int, user_id: int):
    read = MessageRead.query.filter_by(message_id=message_id, user_id=user_id).first()
    if not read:
        read = MessageRead(
            tenant_id=tenant_id,
            message_id=message_id,
            user_id=user_id,
            read_at=datetime.utcnow(),
        )
        db.session.add(read)
        db.session.commit()
    return read
