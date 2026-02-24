from __future__ import annotations

from app.services.communication_service import create_notice, create_reminder


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
        return create_reminder(
            tenant_id=tenant_id,
            title=payload["title"],
            content=payload.get("content", ""),
            remind_at=payload["remind_at"],
            created_by=actor_id,
        )

    return {"status": "noop", "message": f"No executor for action '{action_type}'"}
