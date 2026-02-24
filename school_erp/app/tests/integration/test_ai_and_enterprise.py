def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_ai_approval_and_enterprise_endpoints(client):
    admin_token = login_as(client, "admin", "admin123")

    ai_resp = client.post(
        "/api/v1/ai/chat",
        json={
            "prompt": "Create a notice for tomorrow assembly",
            "action_type": "create_notice",
            "action_payload": {"title": "Assembly", "body": "Assembly at 8:00 AM", "audience": "all"},
        },
        headers=auth_header(admin_token),
    )
    assert ai_resp.status_code == 200
    action = ai_resp.json["data"]["action"]
    assert action["status"] == "pending"

    pending_resp = client.get("/api/v1/ai/actions/pending", headers=auth_header(admin_token))
    assert pending_resp.status_code == 200
    assert len(pending_resp.json["data"]) >= 1

    action_id = pending_resp.json["data"][0]["id"]
    approve_resp = client.post(f"/api/v1/ai/actions/{action_id}/approve", headers=auth_header(admin_token))
    assert approve_resp.status_code == 200
    assert approve_resp.json["data"]["status"] == "executed"

    admission_resp = client.post(
        "/api/v1/admissions/forms",
        json={"student_name": "Test Student", "guardian_name": "Guardian", "target_class": "Class 8"},
        headers=auth_header(admin_token),
    )
    assert admission_resp.status_code == 200

    route_resp = client.post(
        "/api/v1/transport/routes",
        json={"name": "Route B", "shift": "evening"},
        headers=auth_header(admin_token),
    )
    assert route_resp.status_code == 200
