from __future__ import annotations

def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_ai_customer_answer_and_prompt_routing(client):
    parent_token = login_as(client, "parent", "parent123")
    teacher_token = login_as(client, "teacher", "teacher123")
    student_token = login_as(client, "student", "student123")

    # Parent asks a real product question and gets a product-oriented answer.
    parent_answer = client.post(
        "/api/v1/ai/chat",
        json={"prompt": "How much fee is still due for my child?"},
        headers=auth_header(parent_token),
    )
    assert parent_answer.status_code == 200
    assert "fee" in parent_answer.json["data"]["assistant_response"].lower()
    assert "api" not in parent_answer.json["data"]["assistant_response"].lower()
    assert "sql" not in parent_answer.json["data"]["assistant_response"].lower()

    # Teacher routes a reminder workflow by prompt; this should auto-execute (low risk).
    reminder_prompt = client.post(
        "/api/v1/ai/chat",
        json={"prompt": "create reminder title: Class Test Follow-up at: 2026-03-10T09:00:00"},
        headers=auth_header(teacher_token),
    )
    assert reminder_prompt.status_code == 200
    action = reminder_prompt.json["data"].get("action")
    assert action is not None
    assert action["action_type"] == "create_reminder"
    assert action["status"] == "executed"

    reminders = client.get("/api/v1/reminders", headers=auth_header(teacher_token))
    assert reminders.status_code == 200
    assert any(row["title"] == "Class Test Follow-up" for row in reminders.json["data"])

    # Teacher routes event workflow and receives approval-state feedback (medium risk).
    event_prompt = client.post(
        "/api/v1/ai/chat",
        json={
            "prompt": (
                "schedule event title: Science Fair start: 2026-03-15T10:00:00 "
                "end: 2026-03-15T13:00:00 type: competition"
            )
        },
        headers=auth_header(teacher_token),
    )
    assert event_prompt.status_code == 200
    event_action = event_prompt.json["data"].get("action")
    assert event_action is not None
    assert event_action["action_type"] == "schedule_event"
    assert event_action["status"] == "pending"

    # Student cannot route restricted write workflows.
    student_forbidden = client.post(
        "/api/v1/ai/chat",
        json={"prompt": "create notice title: Holiday body: School closed tomorrow audience: all"},
        headers=auth_header(student_token),
    )
    assert student_forbidden.status_code == 200
    response_text = student_forbidden.json["data"]["assistant_response"].lower()
    assert "role" in response_text or "permission" in response_text
    assert student_forbidden.json["data"].get("action") is None
