from __future__ import annotations

from sqlalchemy import func

from app.models.academic import Student
from app.models.attendance import AttendanceRecord
from app.models.communication import Event, Notice, Reminder
from app.models.finance import FeeLedger


def dashboard_summary(tenant_id: int, role: str) -> dict:
    return {
        "role": role,
        "kpis": {
            "students": Student.query.filter_by(tenant_id=tenant_id).count(),
            "notices": Notice.query.filter_by(tenant_id=tenant_id).count(),
            "events": Event.query.filter_by(tenant_id=tenant_id).count(),
            "dues": float(
                db_value_or_zero(
                    FeeLedger.query.with_entities(func.sum(FeeLedger.amount_due - FeeLedger.amount_paid)).filter_by(tenant_id=tenant_id).scalar()
                )
            ),
            "attendance_records": AttendanceRecord.query.filter_by(tenant_id=tenant_id).count(),
        },
        "agenda": [
            {"title": e.title, "starts_at": e.starts_at.isoformat(), "type": e.event_type}
            for e in Event.query.filter_by(tenant_id=tenant_id).order_by(Event.starts_at.desc()).limit(8)
        ],
        "reminders": [
            {"title": r.title, "remind_at": r.remind_at.isoformat()}
            for r in Reminder.query.filter_by(tenant_id=tenant_id).order_by(Reminder.remind_at.asc()).limit(8)
        ],
    }


def db_value_or_zero(value):
    return value if value is not None else 0
