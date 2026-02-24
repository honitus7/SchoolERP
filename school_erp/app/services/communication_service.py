from __future__ import annotations

from app.extensions import db
from app.models.communication import CalendarEntry, Event, Notice, NoticeMedia, Reminder


def create_notice(tenant_id: int, title: str, body: str, posted_by: int, audience: str):
    obj = Notice(
        tenant_id=tenant_id,
        title=title,
        body=body,
        posted_by=posted_by,
        audience=audience,
    )
    db.session.add(obj)
    db.session.commit()
    return obj


def attach_notice_media(tenant_id: int, notice_id: int, media_type: str, file_path: str):
    media = NoticeMedia(
        tenant_id=tenant_id,
        notice_id=notice_id,
        media_type=media_type,
        file_path=file_path,
    )
    db.session.add(media)
    db.session.commit()
    return media


def create_event(tenant_id: int, title: str, details: str, starts_at, ends_at, event_type: str):
    obj = Event(
        tenant_id=tenant_id,
        title=title,
        details=details,
        starts_at=starts_at,
        ends_at=ends_at,
        event_type=event_type,
    )
    db.session.add(obj)
    db.session.commit()
    db.session.add(
        CalendarEntry(
            tenant_id=tenant_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            entry_type="event",
            reference_type="event",
            reference_id=obj.id,
        )
    )
    db.session.commit()
    return obj


def create_reminder(tenant_id: int, title: str, content: str, remind_at, created_by: int):
    obj = Reminder(
        tenant_id=tenant_id,
        title=title,
        content=content,
        remind_at=remind_at,
        created_by=created_by,
    )
    db.session.add(obj)
    db.session.commit()
    db.session.add(
        CalendarEntry(
            tenant_id=tenant_id,
            title=title,
            starts_at=remind_at,
            ends_at=remind_at,
            entry_type="reminder",
            reference_type="reminder",
            reference_id=obj.id,
        )
    )
    db.session.commit()
    return obj
