from __future__ import annotations

from datetime import datetime, timedelta
import re


def _kv_pairs(text: str) -> dict[str, str]:
    keys = [
        "title",
        "body",
        "audience",
        "content",
        "at",
        "time",
        "on",
        "start",
        "end",
        "starts_at",
        "ends_at",
        "type",
        "details",
        "description",
    ]
    pattern = re.compile(rf"\b({'|'.join(keys)})\s*:\s*", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return {}

    pairs: dict[str, str] = {}
    for idx, match in enumerate(matches):
        key = match.group(1).lower()
        value_start = match.end()
        value_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        value = text[value_start:value_end].strip(" ;,\n\t")
        if value:
            pairs[key] = value
    return pairs


def _parse_datetime(value: str | None, fallback_hours: int = 2) -> datetime:
    now = datetime.utcnow()
    if not value:
        return now + timedelta(hours=fallback_hours)

    raw = value.strip().lower()
    if raw == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    # ISO datetime
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        pass

    # Date only
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.replace(hour=9, minute=0, second=0, microsecond=0)
        except ValueError:
            continue

    return now + timedelta(hours=fallback_hours)


def _detect_action(prompt: str) -> dict | None:
    lower = prompt.lower()
    pairs = _kv_pairs(prompt)

    if any(token in lower for token in ["post notice", "create notice", "publish notice", "announce"]):
        title = pairs.get("title") or "New Notice"
        body = pairs.get("body") or prompt
        audience = (pairs.get("audience") or "all").lower()
        if audience not in {"all", "teacher", "parent", "student"}:
            audience = "all"
        return {
            "kind": "action",
            "action_type": "create_notice",
            "payload": {"title": title, "body": body, "audience": audience},
            "allowed_roles": {"admin", "teacher"},
        }

    if any(token in lower for token in ["set reminder", "create reminder", "remind me", "add reminder"]):
        title = pairs.get("title") or "Reminder"
        content = pairs.get("content") or pairs.get("body") or prompt
        remind_at = _parse_datetime(pairs.get("at") or pairs.get("time") or pairs.get("on")).isoformat()
        return {
            "kind": "action",
            "action_type": "create_reminder",
            "payload": {"title": title, "content": content, "remind_at": remind_at},
            "allowed_roles": {"admin", "teacher"},
        }

    if any(token in lower for token in ["schedule event", "create event", "add event", "plan event"]):
        title = pairs.get("title") or "School Event"
        details = pairs.get("details") or pairs.get("description") or prompt
        starts = _parse_datetime(pairs.get("start") or pairs.get("starts_at") or pairs.get("at"), fallback_hours=6)
        ends = _parse_datetime(pairs.get("end") or pairs.get("ends_at"), fallback_hours=7)
        if ends <= starts:
            ends = starts + timedelta(hours=1)
        event_type = pairs.get("type") or "school"
        return {
            "kind": "action",
            "action_type": "schedule_event",
            "payload": {
                "title": title,
                "details": details,
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "event_type": event_type,
            },
            "allowed_roles": {"admin", "teacher"},
        }

    return None


def _detect_query(prompt: str) -> str:
    lower = prompt.lower()

    if any(token in lower for token in ["fee", "dues", "payment", "installment"]):
        return "fees"
    if any(token in lower for token in ["attendance", "present", "absent"]):
        return "attendance"
    if any(token in lower for token in ["report card", "result", "marks", "grade"]):
        return "report_card"
    if any(token in lower for token in ["notice", "announcement"]):
        return "notices"
    if any(token in lower for token in ["event", "calendar", "schedule"]):
        return "events"
    if any(token in lower for token in ["reminder", "task", "deadline"]):
        return "reminders"
    if any(token in lower for token in ["help", "what can you do", "how do i"]):
        return "help"
    return "general"


def route_prompt(prompt: str) -> dict:
    action = _detect_action(prompt)
    if action:
        return action
    return {"kind": "query", "intent": _detect_query(prompt)}
