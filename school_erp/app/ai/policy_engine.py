from __future__ import annotations


HIGH_RISK_ACTIONS = {
    "publish_report_card",
    "post_fee_receipt",
    "assign_role",
    "approve_admission",
    "create_payroll_cycle",
}

MEDIUM_RISK_ACTIONS = {
    "create_notice",
    "create_reminder",
    "schedule_event",
}


def risk_for_action(action_type: str) -> str:
    if action_type in HIGH_RISK_ACTIONS:
        return "high"
    if action_type in MEDIUM_RISK_ACTIONS:
        return "medium"
    return "low"


def requires_approval(risk: str) -> bool:
    return risk in {"medium", "high"}
