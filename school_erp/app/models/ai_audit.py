from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class AiConversation(BaseModel, TenantMixin):
    __tablename__ = "ai_conversations"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(120), nullable=True)


class AiMessage(BaseModel, TenantMixin):
    __tablename__ = "ai_messages"

    conversation_id = db.Column(db.Integer, db.ForeignKey("ai_conversations.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)


class AiActionRequest(BaseModel, TenantMixin):
    __tablename__ = "ai_action_requests"

    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action_type = db.Column(db.String(80), nullable=False)
    risk = db.Column(db.String(10), nullable=False, default="low")
    payload_json = db.Column(db.JSON, nullable=False, default={})
    status = db.Column(db.String(20), nullable=False, default="pending")


class AiActionApproval(BaseModel, TenantMixin):
    __tablename__ = "ai_action_approvals"

    action_request_id = db.Column(db.Integer, db.ForeignKey("ai_action_requests.id"), nullable=False)
    approver_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    decision = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.String(255), nullable=True)


class AuditLog(BaseModel, TenantMixin):
    __tablename__ = "audit_logs"

    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(40), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    details_json = db.Column(db.JSON, nullable=False, default={})
