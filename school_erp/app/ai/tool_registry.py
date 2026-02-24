from __future__ import annotations

TOOLS = {
    "attendance_summary": {
        "description": "Fetch attendance summary for a class or student",
        "risk": "low",
    },
    "fee_due_summary": {
        "description": "Fetch fee due status for a student or linked family profile",
        "risk": "low",
    },
    "draft_notice": {
        "description": "Draft notice text for admin/teacher review",
        "risk": "low",
    },
    "draft_reminder": {
        "description": "Draft reminder message",
        "risk": "low",
    },
    "student_study_plan": {
        "description": "Generate student study plan",
        "risk": "low",
    },
    "create_notice": {
        "description": "Create and publish a notice",
        "risk": "medium",
    },
    "schedule_event": {
        "description": "Create an event and add it to the calendar",
        "risk": "medium",
    },
    "publish_report_card": {
        "description": "Publish final report card",
        "risk": "high",
    },
}
