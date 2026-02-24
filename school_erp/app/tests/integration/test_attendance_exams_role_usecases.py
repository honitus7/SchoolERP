from __future__ import annotations

from app.extensions import db
from app.models.academic import Classroom, Section, Student


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login_as(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json["data"]["tokens"]["access"]


def test_attendance_and_exams_use_cases_across_roles(client, app):
    admin_token = login_as(client, "admin", "admin123")
    teacher_token = login_as(client, "teacher", "teacher123")
    parent_token = login_as(client, "parent", "parent123")
    student_token = login_as(client, "student", "student123")

    # Teacher creates session and marks student attendance.
    session_resp = client.post(
        "/api/v1/attendance/sessions",
        json={"class_id": 1, "section_id": 1, "session_date": "2026-03-01", "source": "manual"},
        headers=auth_header(teacher_token),
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json["data"]["id"]

    record_resp = client.post(
        f"/api/v1/attendance/sessions/{session_id}/records",
        json={"records": [{"student_id": 1, "status": "present", "remarks": "on time"}]},
        headers=auth_header(teacher_token),
    )
    assert record_resp.status_code == 200

    # Parent/student read attendance summaries and records.
    parent_summary = client.get("/api/v1/attendance/my-summary", headers=auth_header(parent_token))
    assert parent_summary.status_code == 200
    assert len(parent_summary.json["data"]) >= 1
    assert parent_summary.json["data"][0]["totals"]["total_sessions"] >= 1

    student_records = client.get("/api/v1/attendance/my-records", headers=auth_header(student_token))
    assert student_records.status_code == 200
    assert any(row["status"] == "present" for row in student_records.json["data"])

    # Teacher/admin can access detailed attendance reports.
    teacher_reports = client.get("/api/v1/attendance/reports?class_id=1", headers=auth_header(teacher_token))
    assert teacher_reports.status_code == 200
    assert any(row["session_id"] == session_id for row in teacher_reports.json["data"])

    # Parent/student cannot perform attendance write actions.
    assert (
        client.post(
            "/api/v1/attendance/sessions",
            json={"class_id": 1, "session_date": "2026-03-02"},
            headers=auth_header(parent_token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/attendance/sessions/{session_id}/records",
            json={"records": [{"student_id": 1, "status": "absent"}]},
            headers=auth_header(student_token),
        ).status_code
        == 403
    )

    # Teacher self attendance and admin review.
    self_mark = client.post(
        "/api/v1/attendance/teacher-self",
        json={"attendance_date": "2026-03-01", "status": "present"},
        headers=auth_header(teacher_token),
    )
    assert self_mark.status_code == 200

    self_list = client.get("/api/v1/attendance/teacher-self", headers=auth_header(teacher_token))
    assert self_list.status_code == 200
    assert any(row["attendance_date"] == "2026-03-01" for row in self_list.json["data"])

    admin_teacher_list = client.get("/api/v1/attendance/teacher-self?teacher_user_id=2", headers=auth_header(admin_token))
    assert admin_teacher_list.status_code == 200
    assert any(row["teacher_user_id"] == 2 for row in admin_teacher_list.json["data"])

    # Teacher exam lifecycle.
    exam_resp = client.post(
        "/api/v1/exams",
        json={"name": "Midterm A", "class_id": 1},
        headers=auth_header(teacher_token),
    )
    assert exam_resp.status_code == 200
    exam_id = exam_resp.json["data"]["id"]

    assert (
        client.post(
            f"/api/v1/exams/{exam_id}/schedule",
            json={"scheduled_from": "2026-03-03", "scheduled_to": "2026-03-05"},
            headers=auth_header(teacher_token),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/exams/{exam_id}/marks",
            json={"subject_id": 1, "entries": [{"student_id": 1, "marks_obtained": 86, "grade": "A"}]},
            headers=auth_header(teacher_token),
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/exams/{exam_id}/publish", headers=auth_header(teacher_token)).status_code == 200

    # Build another class and exam, ensure parent/student class scope is respected.
    with app.app_context():
        class_12 = Classroom(tenant_id=1, name="Class 12", academic_year="2025-26")
        db.session.add(class_12)
        db.session.flush()
        section = Section(tenant_id=1, class_id=class_12.id, name="A")
        db.session.add(section)
        other_student = Student(
            tenant_id=1,
            admission_no="ADM3300",
            full_name="Other Scope Student",
            class_id=class_12.id,
            section_id=section.id,
        )
        db.session.add(other_student)
        db.session.commit()
        class_12_id = class_12.id
        other_student_id = other_student.id

    class_12_exam = client.post(
        "/api/v1/exams",
        json={"name": "Class 12 Midterm", "class_id": class_12_id},
        headers=auth_header(admin_token),
    )
    assert class_12_exam.status_code == 200
    class_12_exam_id = class_12_exam.json["data"]["id"]

    parent_exam_list = client.get("/api/v1/exams", headers=auth_header(parent_token))
    assert parent_exam_list.status_code == 200
    assert any(row["id"] == exam_id for row in parent_exam_list.json["data"])
    assert all(row["id"] != class_12_exam_id for row in parent_exam_list.json["data"])

    student_exam_list = client.get("/api/v1/exams", headers=auth_header(student_token))
    assert student_exam_list.status_code == 200
    assert all(row["id"] != class_12_exam_id for row in student_exam_list.json["data"])

    # Parent/student can view overview and marks only for scoped exam/student.
    assert client.get(f"/api/v1/exams/{exam_id}/overview", headers=auth_header(parent_token)).status_code == 200
    assert client.get(f"/api/v1/exams/{class_12_exam_id}/overview", headers=auth_header(parent_token)).status_code == 403

    parent_marks = client.get(f"/api/v1/exams/{exam_id}/marks", headers=auth_header(parent_token))
    assert parent_marks.status_code == 200
    assert all(row["student_id"] == 1 for row in parent_marks.json["data"])

    assert (
        client.get(
            f"/api/v1/exams/{exam_id}/marks?student_id={other_student_id}",
            headers=auth_header(parent_token),
        ).status_code
        == 403
    )

    # Parent/student can read scoped result lists.
    parent_results = client.get("/api/v1/exams/my-results", headers=auth_header(parent_token))
    assert parent_results.status_code == 200
    assert any(row["exam_id"] == exam_id for row in parent_results.json["data"])

    student_results = client.get("/api/v1/report-cards", headers=auth_header(student_token))
    assert student_results.status_code == 200
    assert all(row["student_id"] == 1 for row in student_results.json["data"])

    # Parent/student cannot perform exam write actions.
    assert (
        client.post("/api/v1/exams", json={"name": "Blocked Exam", "class_id": 1}, headers=auth_header(parent_token)).status_code
        == 403
    )
