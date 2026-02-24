from __future__ import annotations

TOOLS = {
    "attendance_summary": {
        "description": "Fetch attendance summary for a class or student",
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
    "publish_report_card": {
        "description": "Publish final report card",
        "risk": "high",
    },
}
