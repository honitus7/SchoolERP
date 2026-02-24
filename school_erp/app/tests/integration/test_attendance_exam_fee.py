def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_attendance_exam_report_fee_flow(client):
    teacher_token = login_as(client, "teacher", "teacher123")

    session_resp = client.post(
        "/api/v1/attendance/sessions",
        json={"class_id": 1, "session_date": "2026-02-24", "source": "manual"},
        headers=auth_header(teacher_token),
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json["data"]["id"]

    records_resp = client.post(
        f"/api/v1/attendance/sessions/{session_id}/records",
        json={"records": [{"student_id": 1, "status": "present"}]},
        headers=auth_header(teacher_token),
    )
    assert records_resp.status_code == 200

    report_resp = client.post(
        "/api/v1/exams",
        json={"name": "Unit Test", "class_id": 1},
        headers=auth_header(teacher_token),
    )
    assert report_resp.status_code == 200
    exam_id = report_resp.json["data"]["id"]

    schedule_resp = client.post(
        f"/api/v1/exams/{exam_id}/schedule",
        json={"scheduled_from": "2026-02-25", "scheduled_to": "2026-02-27"},
        headers=auth_header(teacher_token),
    )
    assert schedule_resp.status_code == 200

    marks_resp = client.post(
        f"/api/v1/exams/{exam_id}/marks",
        json={"subject_id": 1, "entries": [{"student_id": 1, "marks_obtained": 88, "grade": "A"}]},
        headers=auth_header(teacher_token),
    )
    assert marks_resp.status_code == 200

    publish_resp = client.post(f"/api/v1/exams/{exam_id}/publish", headers=auth_header(teacher_token))
    assert publish_resp.status_code == 200

    card_resp = client.get("/api/v1/report-cards/1", headers=auth_header(teacher_token))
    assert card_resp.status_code == 200
    assert card_resp.json["data"]["percentage"] >= 0

    pdf_resp = client.get("/api/v1/report-cards/1/pdf", headers=auth_header(teacher_token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.content_type == "application/pdf"

    admin_token = login_as(client, "admin", "admin123")
    receipt_resp = client.post(
        "/api/v1/fees/receipts",
        json={"ledger_id": 1, "amount": 3000, "payment_mode": "cash"},
        headers=auth_header(admin_token),
    )
    assert receipt_resp.status_code == 200

    dues_resp = client.get("/api/v1/fees/1/dues", headers=auth_header(admin_token))
    assert dues_resp.status_code == 200
    assert dues_resp.json["data"]["outstanding_due"] >= 0
