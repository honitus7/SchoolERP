from __future__ import annotations

from flask import request

from app.core.auth import current_user
from app.models.ai_audit import AuditLog
from app.extensions import db


def log_audit(action: str, entity_type: str, entity_id: str | None = None, details: dict | None = None) -> None:
    user = current_user()
    record = AuditLog(
        tenant_id=getattr(user, "tenant_id", None),
        actor_user_id=getattr(user, "id", None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=request.remote_addr,
        details_json=details or {},
    )
    db.session.add(record)
    db.session.commit()
