from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.ai.action_executor import execute_action
from app.ai.client_openai import OpenAIClient
from app.ai.policy_engine import requires_approval, risk_for_action
from app.core.audit import log_audit
from app.extensions import db
from app.models.ai_audit import AiActionApproval, AiActionRequest, AiConversation, AiMessage


def ask_ai(tenant_id: int, user_id: int, role: str, prompt: str):
    client = OpenAIClient(current_app.config.get("OPENAI_API_KEY", ""))

    conversation = AiConversation(tenant_id=tenant_id, user_id=user_id, title=prompt[:60])
    db.session.add(conversation)
    db.session.flush()

    db.session.add(AiMessage(tenant_id=tenant_id, conversation_id=conversation.id, role="user", content=prompt))

    system = (
        "You are an ERP copilot. Keep replies concise, role-aware, and safe. "
        "When action is requested, return JSON-like instruction with action_type and payload."
    )
    response = client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Role: {role}. Prompt: {prompt}"},
        ]
    )

    assistant_text = response.get("content", "")
    db.session.add(
        AiMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_text,
        )
    )
    db.session.commit()

    log_audit("ai_chat", "ai_conversations", str(conversation.id), {"prompt": prompt[:120]})
    return conversation, assistant_text


def queue_or_execute_action(tenant_id: int, requested_by: int, action_type: str, payload: dict):
    risk = risk_for_action(action_type)
    req = AiActionRequest(
        tenant_id=tenant_id,
        requested_by=requested_by,
        action_type=action_type,
        risk=risk,
        payload_json=payload,
        status="pending",
    )
    db.session.add(req)
    db.session.flush()

    if requires_approval(risk):
        db.session.commit()
        return req, "pending"

    result = execute_action(action_type, tenant_id, requested_by, payload)
    req.status = "executed"
    db.session.commit()
    log_audit("ai_action_execute", "ai_action_requests", str(req.id), {"result": str(result)[:120]})
    return req, "executed"


def pending_actions(tenant_id: int):
    return AiActionRequest.query.filter_by(tenant_id=tenant_id, status="pending").all()


def decide_action(tenant_id: int, action_id: int, approver_id: int, decision: str, comment: str | None = None):
    action = AiActionRequest.query.filter_by(id=action_id, tenant_id=tenant_id).first_or_404()
    approval = AiActionApproval(
        tenant_id=tenant_id,
        action_request_id=action.id,
        approver_user_id=approver_id,
        decision=decision,
        comment=comment,
    )
    db.session.add(approval)

    if decision == "approve":
        execute_action(action.action_type, tenant_id, action.requested_by, action.payload_json)
        action.status = "executed"
    else:
        action.status = "rejected"

    db.session.commit()
    log_audit(
        "ai_action_decision",
        "ai_action_requests",
        str(action.id),
        {"decision": decision, "at": datetime.utcnow().isoformat()},
    )
    return action
