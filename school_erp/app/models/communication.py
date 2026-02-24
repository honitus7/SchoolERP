from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class Notice(BaseModel, TenantMixin):
    __tablename__ = "notices"

    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    audience = db.Column(db.String(30), nullable=False, default="all")


class NoticeMedia(BaseModel, TenantMixin):
    __tablename__ = "notice_media"

    notice_id = db.Column(db.Integer, db.ForeignKey("notices.id"), nullable=False)
    media_type = db.Column(db.String(20), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)

    notice = db.relationship("Notice", backref="media_items")


class Event(BaseModel, TenantMixin):
    __tablename__ = "events"

    title = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)
    event_type = db.Column(db.String(30), nullable=False, default="school")


class Reminder(BaseModel, TenantMixin):
    __tablename__ = "reminders"

    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=True)
    remind_at = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class CalendarEntry(BaseModel, TenantMixin):
    __tablename__ = "calendar_entries"

    title = db.Column(db.String(120), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)
    entry_type = db.Column(db.String(30), nullable=False)
    reference_type = db.Column(db.String(30), nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)


class Thread(BaseModel, TenantMixin):
    __tablename__ = "threads"

    title = db.Column(db.String(120), nullable=True)
    thread_type = db.Column(db.String(20), nullable=False, default="dm")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class ThreadMember(BaseModel, TenantMixin):
    __tablename__ = "thread_members"

    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    thread = db.relationship("Thread", backref="members")

    __table_args__ = (db.UniqueConstraint("thread_id", "user_id", name="uq_thread_member"),)


class Message(BaseModel, TenantMixin):
    __tablename__ = "messages"

    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)

    thread = db.relationship("Thread", backref="messages")


class MessageRead(BaseModel, TenantMixin):
    __tablename__ = "message_reads"

    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    read_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.UniqueConstraint("message_id", "user_id", name="uq_message_read"),)
