from app.ai.policy_engine import requires_approval, risk_for_action


def test_policy_risk_levels():
    assert risk_for_action("publish_report_card") == "high"
    assert risk_for_action("create_notice") == "medium"
    assert risk_for_action("attendance_summary") == "low"


def test_approval_rules():
    assert requires_approval("high") is True
    assert requires_approval("medium") is True
    assert requires_approval("low") is False
