from __future__ import annotations

from app.extensions import db
from app.models.academic import Classroom, Section, Student


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_end_to_end_role_feature_flows(client, app):
    admin_token = login_as(client, "admin", "admin123")
    teacher_token = login_as(client, "teacher", "teacher123")
    parent_token = login_as(client, "parent", "parent123")
    student_token = login_as(client, "student", "student123")

    # Role-specific dashboard visibility.
    assert client.get("/api/v1/dashboard/admin", headers=auth_header(admin_token)).status_code == 200
    assert client.get("/api/v1/dashboard/teacher", headers=auth_header(teacher_token)).status_code == 200
    assert client.get("/api/v1/dashboard/parent", headers=auth_header(parent_token)).status_code == 200
    assert client.get("/api/v1/dashboard/student", headers=auth_header(student_token)).status_code == 200
    assert client.get("/api/v1/dashboard/admin", headers=auth_header(parent_token)).status_code == 403

    # Add another class/section for scope checks.
    with app.app_context():
        class_11 = Classroom(tenant_id=1, name="Class 11", academic_year="2025-26")
        db.session.add(class_11)
        db.session.flush()
        section_b = Section(tenant_id=1, class_id=class_11.id, name="B")
        db.session.add(section_b)
        db.session.commit()
        class_11_id = class_11.id

    # Parent/student class directory should be scoped to linked student class only.
    admin_classes = client.get("/api/v1/directory/classes", headers=auth_header(admin_token))
    assert admin_classes.status_code == 200
    assert any(row["id"] == class_11_id for row in admin_classes.json["data"])

    parent_classes = client.get("/api/v1/directory/classes", headers=auth_header(parent_token))
    assert parent_classes.status_code == 200
    assert all(row["id"] != class_11_id for row in parent_classes.json["data"])

    student_classes = client.get("/api/v1/directory/classes", headers=auth_header(student_token))
    assert student_classes.status_code == 200
    assert all(row["id"] != class_11_id for row in student_classes.json["data"])

    # Parent/student user directory should expose support contacts, not all users.
    parent_users = client.get("/api/v1/directory/users", headers=auth_header(parent_token))
    assert parent_users.status_code == 200
    parent_usernames = {row["username"] for row in parent_users.json["data"]}
    assert {"parent", "teacher", "admin"} <= parent_usernames
    assert "student" not in parent_usernames

    # Teacher can create attendance session; parent/student cannot.
    session_resp = client.post(
        "/api/v1/attendance/sessions",
        json={"class_id": 1, "section_id": 1, "session_date": "2026-02-24", "source": "ocr"},
        headers=auth_header(teacher_token),
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json["data"]["id"]
    assert (
        client.post(
            "/api/v1/attendance/sessions",
            json={"class_id": 1, "session_date": "2026-02-24"},
            headers=auth_header(parent_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/attendance/sessions",
            json={"class_id": 1, "session_date": "2026-02-24"},
            headers=auth_header(student_token),
        ).status_code
        == 403
    )

    # OCR flow: import -> list -> detail -> map/commit.
    ocr_import = client.post(
        "/api/v1/attendance/ocr/import",
        json={"lines": ["ADM1001 present", "ADM1001 late"]},
        headers=auth_header(teacher_token),
    )
    assert ocr_import.status_code == 200
    batch_id = ocr_import.json["data"]["batch_id"]

    batches = client.get("/api/v1/attendance/ocr/batches", headers=auth_header(teacher_token))
    assert batches.status_code == 200
    assert any(row["id"] == batch_id for row in batches.json["data"])

    detail = client.get(f"/api/v1/attendance/ocr/batches/{batch_id}", headers=auth_header(teacher_token))
    assert detail.status_code == 200
    line_id = detail.json["data"]["lines"][0]["id"]

    commit = client.post(
        f"/api/v1/attendance/ocr/batches/{batch_id}/commit",
        json={"session_id": session_id, "mappings": [{"line_id": line_id, "student_id": 1, "status": "present"}]},
        headers=auth_header(teacher_token),
    )
    assert commit.status_code == 200
    assert commit.json["data"]["status"] == "committed"

    # Teacher exam lifecycle and publish report card.
    exam = client.post(
        "/api/v1/exams",
        json={"name": "Cross Role Test", "class_id": 1},
        headers=auth_header(teacher_token),
    )
    assert exam.status_code == 200
    exam_id = exam.json["data"]["id"]

    schedule = client.post(
        f"/api/v1/exams/{exam_id}/schedule",
        json={"scheduled_from": "2026-03-01", "scheduled_to": "2026-03-02"},
        headers=auth_header(teacher_token),
    )
    assert schedule.status_code == 200

    marks = client.post(
        f"/api/v1/exams/{exam_id}/marks",
        json={"subject_id": 1, "entries": [{"student_id": 1, "marks_obtained": 91, "grade": "A"}]},
        headers=auth_header(teacher_token),
    )
    assert marks.status_code == 200

    publish = client.post(f"/api/v1/exams/{exam_id}/publish", headers=auth_header(teacher_token))
    assert publish.status_code == 200

    # Create exam for another class and validate parent/student scoping.
    class11_exam = client.post(
        "/api/v1/exams",
        json={"name": "Class 11 Test", "class_id": class_11_id},
        headers=auth_header(admin_token),
    )
    assert class11_exam.status_code == 200
    class11_exam_id = class11_exam.json["data"]["id"]

    admin_exam_list = client.get("/api/v1/exams", headers=auth_header(admin_token))
    assert admin_exam_list.status_code == 200
    assert any(row["id"] == class11_exam_id for row in admin_exam_list.json["data"])

    parent_exam_list = client.get("/api/v1/exams", headers=auth_header(parent_token))
    assert parent_exam_list.status_code == 200
    assert all(row["id"] != class11_exam_id for row in parent_exam_list.json["data"])

    student_exam_list = client.get("/api/v1/exams", headers=auth_header(student_token))
    assert student_exam_list.status_code == 200
    assert all(row["id"] != class11_exam_id for row in student_exam_list.json["data"])

    # Notice audience scoping.
    assert (
        client.post(
            "/api/v1/notices",
            json={"title": "Role-All", "body": "All users", "audience": "all"},
            headers=auth_header(admin_token),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/notices",
            json={"title": "Role-Teacher-Only", "body": "Teachers only", "audience": "teacher"},
            headers=auth_header(admin_token),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/notices",
            json={"title": "Role-Parent-Only", "body": "Parents only", "audience": "parent"},
            headers=auth_header(admin_token),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/notices",
            json={"title": "Role-Student-Only", "body": "Students only", "audience": "student"},
            headers=auth_header(admin_token),
        ).status_code
        == 200
    )

    teacher_notices = client.get("/api/v1/notices", headers=auth_header(teacher_token))
    parent_notices = client.get("/api/v1/notices", headers=auth_header(parent_token))
    student_notices = client.get("/api/v1/notices", headers=auth_header(student_token))
    assert teacher_notices.status_code == parent_notices.status_code == student_notices.status_code == 200

    teacher_titles = {row["title"] for row in teacher_notices.json["data"]}
    parent_titles = {row["title"] for row in parent_notices.json["data"]}
    student_titles = {row["title"] for row in student_notices.json["data"]}
    assert "Role-Teacher-Only" in teacher_titles
    assert "Role-Teacher-Only" not in parent_titles
    assert "Role-Teacher-Only" not in student_titles
    assert "Role-Parent-Only" in parent_titles
    assert "Role-Parent-Only" not in teacher_titles
    assert "Role-Student-Only" in student_titles
    assert "Role-Student-Only" not in parent_titles

    # Reminder + calendar role scoping.
    assert (
        client.post(
            "/api/v1/reminders",
            json={"title": "Teacher Private Reminder", "content": "Teacher only", "remind_at": "2026-03-05T09:00:00"},
            headers=auth_header(teacher_token),
        ).status_code
        == 200
    )

    parent_reminders = client.get("/api/v1/reminders", headers=auth_header(parent_token))
    student_reminders = client.get("/api/v1/reminders", headers=auth_header(student_token))
    teacher_reminders = client.get("/api/v1/reminders", headers=auth_header(teacher_token))
    assert parent_reminders.status_code == student_reminders.status_code == teacher_reminders.status_code == 200

    parent_reminder_titles = {row["title"] for row in parent_reminders.json["data"]}
    student_reminder_titles = {row["title"] for row in student_reminders.json["data"]}
    teacher_reminder_titles = {row["title"] for row in teacher_reminders.json["data"]}
    assert "Teacher Private Reminder" in teacher_reminder_titles
    assert "Teacher Private Reminder" not in parent_reminder_titles
    assert "Teacher Private Reminder" not in student_reminder_titles

    parent_calendar = client.get("/api/v1/calendar", headers=auth_header(parent_token))
    teacher_calendar = client.get("/api/v1/calendar", headers=auth_header(teacher_token))
    assert parent_calendar.status_code == teacher_calendar.status_code == 200
    assert all(row["title"] != "Teacher Private Reminder" for row in parent_calendar.json["data"])
    assert any(row["title"] == "Teacher Private Reminder" for row in teacher_calendar.json["data"])

    # Parent and student can access their own data.
    assert client.get("/api/v1/report-cards/1", headers=auth_header(parent_token)).status_code == 200
    assert client.get("/api/v1/report-cards/1", headers=auth_header(student_token)).status_code == 200
    assert client.get("/api/v1/fees/1/dues", headers=auth_header(parent_token)).status_code == 200
    assert client.get("/api/v1/fees/1/dues", headers=auth_header(student_token)).status_code == 200

    # Create another student and verify parent/student cannot access it.
    with app.app_context():
        other_student = Student(
            tenant_id=1,
            admission_no="ADM2002",
            full_name="Other Student",
            class_id=1,
            section_id=1,
        )
        db.session.add(other_student)
        db.session.commit()
        other_student_id = other_student.id

    assert client.get(f"/api/v1/fees/{other_student_id}/dues", headers=auth_header(parent_token)).status_code == 403
    assert client.get(f"/api/v1/fees/{other_student_id}/dues", headers=auth_header(student_token)).status_code == 403
    assert client.get(f"/api/v1/report-cards/{other_student_id}", headers=auth_header(parent_token)).status_code == 403
    assert client.get(f"/api/v1/report-cards/{other_student_id}", headers=auth_header(student_token)).status_code == 403

    # Enterprise write endpoints remain admin-only.
    assert (
        client.post("/api/v1/payroll/cycles", json={"month_label": "2026-04"}, headers=auth_header(teacher_token)).status_code
        == 403
    )
    assert (
        client.post("/api/v1/transport/routes", json={"name": "Route Z"}, headers=auth_header(teacher_token)).status_code
        == 403
    )
    assert (
        client.post("/api/v1/payroll/cycles", json={"month_label": "2026-04"}, headers=auth_header(admin_token)).status_code
        == 200
    )
