def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_module_api_coverage_admin_core(client):
    admin_token = login_as(client, "admin", "admin123")
    headers = auth_header(admin_token)
    parent_token = login_as(client, "parent", "parent123")
    teacher_token = login_as(client, "teacher", "teacher123")

    for path in [
        "/api/v1/directory/classes",
        "/api/v1/directory/students",
        "/api/v1/directory/subjects",
        "/api/v1/directory/users",
        "/api/v1/attendance/sessions",
        "/api/v1/exams",
        "/api/v1/fees/structures",
        "/api/v1/fees/installments",
        "/api/v1/reminders",
        "/api/v1/messages/threads",
        "/api/v1/calendar",
    ]:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, path

    admission = client.post(
        "/api/v1/admissions/forms",
        json={"student_name": "Coverage Kid", "guardian_name": "Coverage Parent", "target_class": "Class 9"},
        headers=headers,
    )
    assert admission.status_code == 200
    form_id = admission.json["data"]["id"]

    status = client.patch(
        f"/api/v1/admissions/forms/{form_id}/status",
        json={"status": "approved"},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json["data"]["status"] == "approved"

    route = client.post("/api/v1/transport/routes", json={"name": "Route C"}, headers=headers)
    assert route.status_code == 200
    route_id = route.json["data"]["id"]

    vehicle = client.post(
        "/api/v1/transport/vehicles",
        json={"registration_no": "MH01AB1234", "capacity": 40},
        headers=headers,
    )
    assert vehicle.status_code == 200

    stop = client.post(
        "/api/v1/transport/stops",
        json={"route_id": route_id, "stop_name": "Main Gate", "stop_order": 1},
        headers=headers,
    )
    assert stop.status_code == 200

    payroll_cycle = client.post("/api/v1/payroll/cycles", json={"month_label": "2026-03"}, headers=headers)
    assert payroll_cycle.status_code == 200
    cycle_id = payroll_cycle.json["data"]["id"]

    payroll_entry = client.post(
        "/api/v1/payroll/entries",
        json={"cycle_id": cycle_id, "teacher_user_id": 2, "gross_pay": 50000, "net_pay": 47000},
        headers=headers,
    )
    assert payroll_entry.status_code == 200

    hostel = client.post("/api/v1/hostel/hostels", json={"name": "Girls Hostel"}, headers=headers)
    assert hostel.status_code == 200
    hostel_id = hostel.json["data"]["id"]

    room = client.post(
        "/api/v1/hostel/rooms",
        json={"hostel_id": hostel_id, "room_no": "G-101", "capacity": 3},
        headers=headers,
    )
    assert room.status_code == 200

    item = client.post(
        "/api/v1/inventory/items",
        json={"name": "Whiteboard Marker", "sku": "WBM-1", "quantity": 20},
        headers=headers,
    )
    assert item.status_code == 200
    item_id = item.json["data"]["id"]

    move = client.post(
        "/api/v1/inventory/stock-moves",
        json={"item_id": item_id, "move_type": "out", "quantity": 2, "notes": "Classroom use"},
        headers=headers,
    )
    assert move.status_code == 200

    course = client.post(
        "/api/v1/coaching/courses",
        json={"code": "JEE-26", "title": "JEE Foundation"},
        headers=headers,
    )
    assert course.status_code == 200
    course_id = course.json["data"]["id"]

    batch = client.post(
        "/api/v1/coaching/batches",
        json={"course_id": course_id, "name": "Morning Batch", "timing": "07:00 AM"},
        headers=headers,
    )
    assert batch.status_code == 200
    batch_id = batch.json["data"]["id"]

    series = client.post(
        "/api/v1/coaching/test-series",
        json={"batch_id": batch_id, "title": "Weekly Mock 1", "total_marks": 300},
        headers=headers,
    )
    assert series.status_code == 200
    series_id = series.json["data"]["id"]

    attempt = client.post(
        "/api/v1/coaching/test-attempts",
        json={"test_series_id": series_id, "student_id": 1, "score": 228},
        headers=headers,
    )
    assert attempt.status_code == 200

    thread = client.post(
        "/api/v1/messages/threads",
        json={"thread_type": "group", "title": "Admin-Teacher", "member_ids": [2]},
        headers=headers,
    )
    assert thread.status_code == 200
    thread_id = thread.json["data"]["id"]

    sent = client.post(
        f"/api/v1/messages/threads/{thread_id}/messages",
        json={"body": "Coverage message"},
        headers=headers,
    )
    assert sent.status_code == 200

    forbidden = client.get(
        f"/api/v1/messages/threads/{thread_id}/messages",
        headers=auth_header(parent_token),
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        f"/api/v1/messages/threads/{thread_id}/messages",
        headers=auth_header(teacher_token),
    )
    assert allowed.status_code == 200
