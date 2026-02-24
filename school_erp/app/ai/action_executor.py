from __future__ import annotations

from datetime import datetime

from app.services.communication_service import create_event, create_notice, create_reminder


def _to_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.utcnow()
    return datetime.utcnow()


def execute_action(action_type: str, tenant_id: int, actor_id: int, payload: dict):
    if action_type == "create_notice":
        return create_notice(
            tenant_id=tenant_id,
            title=payload["title"],
            body=payload["body"],
            posted_by=actor_id,
            audience=payload.get("audience", "all"),
        )

    if action_type == "create_reminder":
        remind_at = _to_datetime(payload["remind_at"])
        return create_reminder(
            tenant_id=tenant_id,
            title=payload["title"],
            content=payload.get("content", ""),
            remind_at=remind_at,
            created_by=actor_id,
        )

    if action_type == "schedule_event":
        starts_at = _to_datetime(payload.get("starts_at"))
        ends_at = _to_datetime(payload.get("ends_at"))
        if ends_at <= starts_at:
            ends_at = starts_at
        return create_event(
            tenant_id=tenant_id,
            title=payload.get("title") or "School Event",
            details=payload.get("details", ""),
            starts_at=starts_at,
            ends_at=ends_at,
            event_type=payload.get("event_type", "school"),
        )

    return {"status": "noop", "message": f"No executor for action '{action_type}'"}
