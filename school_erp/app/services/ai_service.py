from __future__ import annotations

from datetime import datetime

from flask import current_app
from sqlalchemy import func

from app.ai.action_executor import execute_action
from app.ai.client_openai import OpenAIClient
from app.ai.policy_engine import requires_approval, risk_for_action
from app.ai.product_router import route_prompt
from app.core.audit import log_audit
from app.extensions import db
from app.models.academic import Guardian, Student, StudentGuardian
from app.models.ai_audit import AiActionApproval, AiActionRequest, AiConversation, AiMessage
from app.models.attendance import AttendanceRecord
from app.models.communication import Event, Notice, Reminder
from app.models.exams import ReportCard
from app.models.finance import FeeLedger
from app.models.identity import Role, User


def _student_scope_ids(user: User) -> list[int] | None:
    if user.has_role("admin") or user.has_role("teacher"):
        return None

    if user.has_role("student"):
        rows = Student.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).all()
        return [row.id for row in rows]

    if user.has_role("parent"):
        guardian = Guardian.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).first()
        if not guardian:
            return []
        rows = StudentGuardian.query.filter_by(tenant_id=user.tenant_id, guardian_id=guardian.id).all()
        return [row.student_id for row in rows]

    return []


def _student_name_map(tenant_id: int, student_ids: list[int] | None = None) -> dict[int, str]:
    query = Student.query.filter_by(tenant_id=tenant_id)
    if student_ids is not None:
        if not student_ids:
            return {}
        query = query.filter(Student.id.in_(student_ids))
    rows = query.all()
    return {row.id: row.full_name for row in rows}


def _notice_visible_to_user(user: User, notice: Notice) -> bool:
    if user.has_role("admin"):
        return True
    tokens = {
        token.strip().lower()
        for token in (notice.audience or "all").replace("|", ",").split(",")
        if token.strip()
    }
    if not tokens:
        tokens = {"all"}
    role_tokens = {role.name.lower() for role in user.roles}
    return bool({"all", "everyone"} & tokens) or bool(role_tokens & tokens)


def _visible_reminder_creator_ids(user: User) -> list[int] | None:
    if user.has_role("admin"):
        return None

    admin_ids = [
        row.id
        for row in User.query.filter(
            User.tenant_id == user.tenant_id,
            User.roles.any(Role.name == "admin"),
        ).all()
    ]
    creator_ids = set(admin_ids)
    creator_ids.add(user.id)
    return sorted(creator_ids)


def _capabilities_response(role: str) -> str:
    return (
        f"You are signed in as {role}. I can answer questions about attendance, fees, report cards, "
        "notices, reminders, and upcoming events. I can also route workflows when prompted, for example: "
        "'create reminder title: Fee follow-up at: 2026-03-01T09:00:00', "
        "'post notice title: PTM body: Parent meeting on Saturday audience: parent', or "
        "'schedule event title: Science Fair start: 2026-03-05T10:00:00 end: 2026-03-05T13:00:00'."
    )


def _fees_answer(user: User) -> str:
    student_ids = _student_scope_ids(user)
    if student_ids is None:
        due = (
            db.session.query(func.sum(FeeLedger.amount_due - FeeLedger.amount_paid))
            .filter(FeeLedger.tenant_id == user.tenant_id)
            .scalar()
            or 0
        )
        overdue_count = FeeLedger.query.filter_by(tenant_id=user.tenant_id, status="overdue").count()
        return (
            f"Current fee overview: outstanding dues are {round(float(due), 2)} across the institution, "
            f"with {overdue_count} overdue ledger entries."
        )

    if not student_ids:
        return "I could not find any linked student profile for fee tracking."

    names = _student_name_map(user.tenant_id, student_ids)
    rows = (
        db.session.query(
            FeeLedger.student_id,
            func.sum(FeeLedger.amount_due - FeeLedger.amount_paid),
        )
        .filter(FeeLedger.tenant_id == user.tenant_id, FeeLedger.student_id.in_(student_ids))
        .group_by(FeeLedger.student_id)
        .all()
    )
    if not rows:
        return "No active fee ledger entries were found for your linked student profile."

    parts = []
    for student_id, due in rows:
        parts.append(f"{names.get(student_id, f'Student {student_id}')}: {round(float(due or 0), 2)} due")
    return "Fee status summary: " + "; ".join(parts) + "."


def _attendance_answer(user: User) -> str:
    student_ids = _student_scope_ids(user)
    if student_ids is None:
        total = AttendanceRecord.query.filter_by(tenant_id=user.tenant_id).count()
        present = AttendanceRecord.query.filter_by(tenant_id=user.tenant_id, status="present").count()
        percentage = round((present / total * 100), 1) if total else 0
        return f"Attendance snapshot: {present} present records out of {total}, with {percentage}% present status."

    if not student_ids:
        return "I could not find any linked student profile for attendance."

    names = _student_name_map(user.tenant_id, student_ids)
    lines = []
    for student_id in student_ids:
        total = AttendanceRecord.query.filter_by(tenant_id=user.tenant_id, student_id=student_id).count()
        present = AttendanceRecord.query.filter_by(
            tenant_id=user.tenant_id,
            student_id=student_id,
            status="present",
        ).count()
        percentage = round((present / total * 100), 1) if total else 0
        lines.append(f"{names.get(student_id, f'Student {student_id}')}: {present}/{total} present ({percentage}%)")
    return "Attendance summary: " + "; ".join(lines) + "."


def _report_card_answer(user: User) -> str:
    student_ids = _student_scope_ids(user)
    names = _student_name_map(user.tenant_id, student_ids)

    query = ReportCard.query.filter_by(tenant_id=user.tenant_id).order_by(ReportCard.created_at.desc())
    if student_ids is not None:
        if not student_ids:
            return "No linked student profile was found for report-card insights."
        query = query.filter(ReportCard.student_id.in_(student_ids))

    rows = query.limit(5).all()
    if not rows:
        return "No published report card is currently available."

    parts = []
    for row in rows:
        parts.append(
            f"{names.get(row.student_id, f'Student {row.student_id}')}: "
            f"{round(float(row.percentage or 0), 1)}% ({row.status})"
        )
    return "Latest report card highlights: " + "; ".join(parts) + "."


def _notices_answer(user: User) -> str:
    rows = Notice.query.filter_by(tenant_id=user.tenant_id).order_by(Notice.created_at.desc()).limit(12).all()
    visible = [row for row in rows if _notice_visible_to_user(user, row)]
    if not visible:
        return "There are no visible notices for your role at the moment."
    highlights = [f"{row.title} ({row.audience})" for row in visible[:5]]
    return "Recent notices: " + "; ".join(highlights) + "."


def _events_answer(user: User) -> str:
    rows = Event.query.filter_by(tenant_id=user.tenant_id).order_by(Event.starts_at.asc()).limit(5).all()
    if not rows:
        return "No upcoming events are scheduled right now."
    highlights = [f"{row.title} on {row.starts_at.strftime('%d %b %Y %H:%M')}" for row in rows]
    return "Upcoming events: " + "; ".join(highlights) + "."


def _reminders_answer(user: User) -> str:
    query = Reminder.query.filter_by(tenant_id=user.tenant_id)
    creator_ids = _visible_reminder_creator_ids(user)
    if creator_ids is not None:
        query = query.filter(Reminder.created_by.in_(creator_ids))
    rows = query.order_by(Reminder.remind_at.asc()).limit(5).all()
    if not rows:
        return "No reminders are pending for your role."
    highlights = [f"{row.title} at {row.remind_at.strftime('%d %b %Y %H:%M')}" for row in rows]
    return "Upcoming reminders: " + "; ".join(highlights) + "."


def _general_llm_response(role: str, prompt: str) -> str:
    api_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _capabilities_response(role)

    client = OpenAIClient(api_key)
    response = client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You are an ERP product copilot for schools and coaching centers. "
                    "Reply in practical customer-support language, role-aware, concise, and friendly. "
                    "Never expose raw API routes, SQL, or internal database implementation details."
                ),
            },
            {"role": "user", "content": f"Role: {role}. Prompt: {prompt}"},
        ]
    )
    text = (response.get("content") or "").strip()
    return text or _capabilities_response(role)


def _intent_response(user: User, role: str, intent: str, prompt: str) -> str:
    if intent == "fees":
        return _fees_answer(user)
    if intent == "attendance":
        return _attendance_answer(user)
    if intent == "report_card":
        return _report_card_answer(user)
    if intent == "notices":
        return _notices_answer(user)
    if intent == "events":
        return _events_answer(user)
    if intent == "reminders":
        return _reminders_answer(user)
    if intent == "help":
        return _capabilities_response(role)
    return _general_llm_response(role, prompt)


def _friendly_action_message(action_type: str, state: str) -> str:
    names = {
        "create_notice": "notice",
        "create_reminder": "reminder",
        "schedule_event": "event",
    }
    label = names.get(action_type, "workflow action")
    if state == "executed":
        return f"Done. I have completed the {label} workflow."
    return f"I have prepared the {label} request. It is now waiting for approval."


def ask_ai(tenant_id: int, user_id: int, role: str, prompt: str, enable_routing: bool = True):
    user = db.session.get(User, user_id)
    role = role.lower()

    conversation = AiConversation(tenant_id=tenant_id, user_id=user_id, title=prompt[:60])
    db.session.add(conversation)
    db.session.flush()

    db.session.add(AiMessage(tenant_id=tenant_id, conversation_id=conversation.id, role="user", content=prompt))

    route = route_prompt(prompt) if enable_routing else {"kind": "query", "intent": "general"}
    routed_action: dict | None = None

    if route.get("kind") == "action":
        allowed_roles = route.get("allowed_roles", set())
        if role not in allowed_roles:
            assistant_text = "Your role is read-only for this workflow. Please contact an authorized admin or teacher."
        else:
            request_obj, state = queue_or_execute_action(
                tenant_id=tenant_id,
                requested_by=user_id,
                action_type=route["action_type"],
                payload=route["payload"],
            )
            routed_action = {
                "id": request_obj.id,
                "action_type": request_obj.action_type,
                "risk": request_obj.risk,
                "status": state,
            }
            assistant_text = _friendly_action_message(route["action_type"], state)
    else:
        assistant_text = _intent_response(user, role, route.get("intent", "general"), prompt)

    db.session.add(
        AiMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_text,
        )
    )
    db.session.commit()

    log_audit(
        "ai_chat",
        "ai_conversations",
        str(conversation.id),
        {"prompt": prompt[:120], "route_kind": route.get("kind"), "intent": route.get("intent")},
    )
    return conversation, assistant_text, routed_action


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
