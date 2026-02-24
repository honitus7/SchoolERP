from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from flask import current_app, request, send_file
from sqlalchemy import and_, or_

from app.blueprints.api_v1 import bp
from app.core.auth import current_user
from app.core.rbac import role_required
from app.core.responses import fail, ok
from app.core.validators import require_fields
from app.extensions import db
from app.models.academic import Classroom, Guardian, Section, Student, StudentGuardian, Subject
from app.models.attendance import AttendanceRecord, AttendanceSession, OcrImportBatch, OcrLine, TeacherAttendance
from app.models.communication import CalendarEntry, Event, Message, MessageRead, Notice, Reminder, Thread, ThreadMember
from app.models.enterprise import AdmissionForm, Room
from app.models.exams import Exam, ExamSubject, Mark, ReportCard
from app.models.finance import FeeInstallment, FeeLedger, FeeStructure
from app.models.identity import Role, User
from app.services.ai_service import ask_ai, decide_action, pending_actions, queue_or_execute_action
from app.services.attendance_service import create_ocr_batch, create_session, mark_teacher_self, upsert_records
from app.services.communication_service import attach_notice_media, create_event, create_notice, create_reminder
from app.services.dashboard_service import dashboard_summary
from app.services.enterprise_service import admission_status_update, create_record, list_records
from app.services.exam_service import add_marks, create_exam, publish_report_cards, schedule_exam
from app.services.fees_service import create_installment, create_receipt, create_structure, ledgers_for_student
from app.services.messaging_service import create_thread, mark_read, post_message
from app.services.report_service import render_report_card_pdf
from app.tasks.ocr_jobs import extract_lines


def _serialize(obj, fields: list[str]) -> dict:
    data = {}
    for field in fields:
        value = getattr(obj, field)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        data[field] = value
    return data


def _parse_csv_ints(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


def _thread_member_exists(tenant_id: int, thread_id: int, user_id: int) -> bool:
    membership = ThreadMember.query.filter_by(
        tenant_id=tenant_id,
        thread_id=thread_id,
        user_id=user_id,
    ).first()
    return membership is not None


def _allowed_student_ids_for_user(user: User) -> list[int] | None:
    if user.has_role("admin") or user.has_role("teacher"):
        return None

    if user.has_role("student"):
        rows = Student.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).all()
        return [row.id for row in rows]

    if user.has_role("parent"):
        guardian = Guardian.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).first()
        if not guardian:
            return []
        links = StudentGuardian.query.filter_by(tenant_id=user.tenant_id, guardian_id=guardian.id).all()
        return [link.student_id for link in links]

    return []


def _is_student_in_scope(user: User, student_id: int) -> bool:
    allowed = _allowed_student_ids_for_user(user)
    if allowed is None:
        return True
    return student_id in set(allowed)


def _allowed_class_ids_for_user(user: User) -> list[int] | None:
    if user.has_role("admin") or user.has_role("teacher"):
        return None

    allowed_students = _allowed_student_ids_for_user(user) or []
    if not allowed_students:
        return []

    class_ids = (
        db.session.query(Student.class_id)
        .filter(
            Student.tenant_id == user.tenant_id,
            Student.id.in_(allowed_students),
            Student.class_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return [row[0] for row in class_ids]


def _visible_roles_for_user(user: User) -> set[str]:
    return {r.name.lower() for r in user.roles}


def _notice_visible_to_user(user: User, notice: Notice) -> bool:
    if user.has_role("admin"):
        return True

    tokens = {
        token.strip().lower()
        for token in (notice.audience or "all").replace("|", ",").split(",")
        if token.strip()
    }
    if not tokens:
        tokens = {"all"}

    role_tokens = _visible_roles_for_user(user)
    return bool({"all", "everyone"} & tokens) or bool(role_tokens & tokens)


def _visible_reminder_creator_ids(user: User) -> list[int] | None:
    if user.has_role("admin"):
        return None

    admin_ids = [
        row.id
        for row in User.query.filter(
            User.tenant_id == user.tenant_id,
            User.roles.any(Role.name == "admin"),
        ).all()
    ]
    creator_ids = set(admin_ids)
    creator_ids.add(user.id)
    return sorted(creator_ids)


def _is_exam_in_scope(user: User, exam: Exam) -> bool:
    class_ids = _allowed_class_ids_for_user(user)
    if class_ids is None:
        return True
    return exam.class_id in set(class_ids)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _attendance_summary_for_student(tenant_id: int, student_id: int, date_from: date | None = None, date_to: date | None = None) -> dict:
    query = AttendanceRecord.query.join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id).filter(
        AttendanceRecord.tenant_id == tenant_id,
        AttendanceRecord.student_id == student_id,
    )
    if date_from:
        query = query.filter(AttendanceSession.session_date >= date_from)
    if date_to:
        query = query.filter(AttendanceSession.session_date <= date_to)

    rows = query.order_by(AttendanceSession.session_date.desc()).limit(400).all()
    total = len(rows)
    present = sum(1 for row in rows if row.status == "present")
    absent = sum(1 for row in rows if row.status == "absent")
    late = sum(1 for row in rows if row.status == "late")
    percentage = round((present / total * 100), 2) if total else 0
    student = db.session.get(Student, student_id)

    recent = []
    for row in rows[:20]:
        recent.append(
            {
                "record_id": row.id,
                "session_id": row.session_id,
                "session_date": row.session.session_date.isoformat() if row.session else None,
                "status": row.status,
                "remarks": row.remarks,
                "subject_id": row.session.subject_id if row.session else None,
            }
        )

    return {
        "student_id": student_id,
        "student_name": student.full_name if student else f"Student-{student_id}",
        "totals": {
            "total_sessions": total,
            "present": present,
            "absent": absent,
            "late": late,
            "attendance_percentage": percentage,
        },
        "recent_records": recent,
    }


@bp.get("/health")
def health():
    return ok({"status": "ok", "service": "school-erp-api"})


@bp.get("/dashboard/<role>")
@role_required("admin", "teacher", "parent", "student")
def api_dashboard(role: str):
    user = current_user()
    role = role.lower()
    user_roles = {r.name.lower() for r in user.roles}
    if role not in user_roles and "admin" not in user_roles:
        return fail("Forbidden", status=403, code="forbidden")
    return ok(dashboard_summary(user.tenant_id, role))


@bp.get("/directory/classes")
@role_required("admin", "teacher", "parent", "student")
def api_directory_classes():
    user = current_user()
    query = Classroom.query.filter_by(tenant_id=user.tenant_id)
    class_ids = _allowed_class_ids_for_user(user)
    if class_ids is not None:
        if not class_ids:
            return ok([])
        query = query.filter(Classroom.id.in_(class_ids))

    classes = query.order_by(Classroom.name.asc()).all()
    data = []
    for cls in classes:
        data.append(
            {
                "id": cls.id,
                "name": cls.name,
                "academic_year": cls.academic_year,
                "sections": [{"id": s.id, "name": s.name} for s in Section.query.filter_by(tenant_id=user.tenant_id, class_id=cls.id)],
            }
        )
    return ok(data)


@bp.get("/directory/students")
@role_required("admin", "teacher", "parent", "student")
def api_directory_students():
    user = current_user()
    query = Student.query.filter_by(tenant_id=user.tenant_id)
    allowed = _allowed_student_ids_for_user(user)
    if allowed is not None:
        if not allowed:
            return ok([])
        query = query.filter(Student.id.in_(allowed))
    rows = query.order_by(Student.full_name.asc()).limit(500).all()
    return ok(
        [
            {
                "id": x.id,
                "admission_no": x.admission_no,
                "full_name": x.full_name,
                "class_id": x.class_id,
                "section_id": x.section_id,
            }
            for x in rows
        ]
    )


@bp.get("/directory/subjects")
@role_required("admin", "teacher", "parent", "student")
def api_directory_subjects():
    user = current_user()
    rows = Subject.query.filter_by(tenant_id=user.tenant_id).order_by(Subject.name.asc()).all()
    return ok([{"id": s.id, "code": s.code, "name": s.name} for s in rows])


@bp.get("/directory/users")
@role_required("admin", "teacher", "parent", "student")
def api_directory_users():
    user = current_user()
    query = User.query.filter_by(tenant_id=user.tenant_id)
    if not (user.has_role("admin") or user.has_role("teacher")):
        query = query.filter(
            or_(
                User.id == user.id,
                User.roles.any(Role.name.in_(["teacher", "admin"])),
            )
        )

    rows = query.order_by(User.full_name.asc()).limit(500).all()
    return ok(
        [
            {
                "id": x.id,
                "username": x.username,
                "full_name": x.full_name,
                "roles": [r.name for r in x.roles],
            }
            for x in rows
        ]
    )


@bp.post("/attendance/sessions")
@role_required("admin", "teacher")
def api_attendance_session_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["class_id", "session_date"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    session = create_session(
        tenant_id=user.tenant_id,
        class_id=payload["class_id"],
        section_id=payload.get("section_id"),
        subject_id=payload.get("subject_id"),
        session_date=date.fromisoformat(payload["session_date"]),
        source=payload.get("source", "manual"),
        created_by=user.id,
    )
    return ok(_serialize(session, ["id", "class_id", "section_id", "subject_id", "session_date", "source"]))


@bp.get("/attendance/sessions")
@role_required("admin", "teacher")
def api_attendance_session_list():
    user = current_user()
    rows = AttendanceSession.query.filter_by(tenant_id=user.tenant_id).order_by(AttendanceSession.session_date.desc()).limit(200).all()
    return ok([_serialize(r, ["id", "class_id", "section_id", "subject_id", "session_date", "source", "created_by"]) for r in rows])


@bp.post("/attendance/sessions/<int:session_id>/records")
@role_required("admin", "teacher")
def api_attendance_records_upsert(session_id: int):
    payload = request.get_json(silent=True) or {}
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        return fail("records must be a non-empty list")

    user = current_user()
    try:
        upsert_records(user.tenant_id, session_id, records)
    except ValueError as exc:
        return fail(str(exc), status=404, code="not_found")
    return ok({"session_id": session_id, "updated": len(records)})


@bp.post("/attendance/teacher-self")
@role_required("teacher", "admin")
def api_teacher_attendance():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["attendance_date", "status"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    record = mark_teacher_self(
        tenant_id=user.tenant_id,
        teacher_user_id=user.id,
        attendance_date=date.fromisoformat(payload["attendance_date"]),
        status=payload["status"],
    )
    return ok(_serialize(record, ["id", "teacher_user_id", "attendance_date", "status"]))


@bp.get("/attendance/teacher-self")
@role_required("teacher", "admin")
def api_teacher_attendance_list():
    user = current_user()
    teacher_user_id = request.args.get("teacher_user_id", type=int)
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))

    query = TeacherAttendance.query.filter_by(tenant_id=user.tenant_id)
    if user.has_role("teacher"):
        query = query.filter(TeacherAttendance.teacher_user_id == user.id)
    elif teacher_user_id:
        query = query.filter(TeacherAttendance.teacher_user_id == teacher_user_id)

    if date_from:
        query = query.filter(TeacherAttendance.attendance_date >= date_from)
    if date_to:
        query = query.filter(TeacherAttendance.attendance_date <= date_to)

    rows = query.order_by(TeacherAttendance.attendance_date.desc()).limit(300).all()
    return ok([_serialize(row, ["id", "teacher_user_id", "attendance_date", "status"]) for row in rows])


@bp.post("/attendance/ocr/import")
@role_required("admin", "teacher")
def api_attendance_ocr_import():
    user = current_user()
    upload = request.files.get("file")
    payload = request.form.to_dict() if upload else (request.get_json(silent=True) or {})

    lines: list[str] = payload.get("lines", []) if isinstance(payload.get("lines"), list) else []
    file_path = ""
    if upload:
        safe_name = f"{uuid4().hex}_{upload.filename}"
        target = Path(current_app.config["UPLOAD_FOLDER"]) / safe_name
        upload.save(target)
        file_path = str(target)
        lines = extract_lines(file_path)

    batch = create_ocr_batch(
        tenant_id=user.tenant_id,
        uploaded_by=user.id,
        file_path=file_path or "manual_lines",
        extracted_lines=lines,
    )
    return ok({"batch_id": batch.id, "lines": len(lines), "status": batch.parse_status})


@bp.get("/attendance/ocr/batches")
@role_required("admin", "teacher")
def api_attendance_ocr_batch_list():
    user = current_user()
    rows = (
        OcrImportBatch.query.filter_by(tenant_id=user.tenant_id)
        .order_by(OcrImportBatch.created_at.desc())
        .limit(100)
        .all()
    )
    data = []
    for row in rows:
        data.append(
            {
                "id": row.id,
                "uploaded_by": row.uploaded_by,
                "file_path": row.file_path,
                "parse_status": row.parse_status,
                "notes": row.notes,
                "line_count": OcrLine.query.filter_by(tenant_id=user.tenant_id, batch_id=row.id).count(),
                "created_at": row.created_at.isoformat(),
            }
        )
    return ok(data)


@bp.get("/attendance/ocr/batches/<int:batch_id>")
@role_required("admin", "teacher")
def api_attendance_ocr_batch_detail(batch_id: int):
    user = current_user()
    batch = OcrImportBatch.query.filter_by(tenant_id=user.tenant_id, id=batch_id).first()
    if not batch:
        return fail("OCR batch not found", status=404, code="not_found")

    lines = OcrLine.query.filter_by(tenant_id=user.tenant_id, batch_id=batch.id).order_by(OcrLine.id.asc()).all()
    return ok(
        {
            "id": batch.id,
            "uploaded_by": batch.uploaded_by,
            "file_path": batch.file_path,
            "parse_status": batch.parse_status,
            "notes": batch.notes,
            "created_at": batch.created_at.isoformat(),
            "lines": [
                {
                    "id": line.id,
                    "raw_text": line.raw_text,
                    "mapped_student_id": line.mapped_student_id,
                    "mapped_status": line.mapped_status,
                }
                for line in lines
            ],
        }
    )


@bp.post("/attendance/ocr/batches/<int:batch_id>/commit")
@role_required("admin", "teacher")
def api_attendance_ocr_batch_commit(batch_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["session_id"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    mappings = payload.get("mappings", [])
    if mappings is None:
        mappings = []
    if not isinstance(mappings, list):
        return fail("mappings must be a list")

    user = current_user()
    batch = OcrImportBatch.query.filter_by(tenant_id=user.tenant_id, id=batch_id).first()
    if not batch:
        return fail("OCR batch not found", status=404, code="not_found")

    line_updates = 0
    for entry in mappings:
        line_id = entry.get("line_id")
        student_id = entry.get("student_id")
        if not line_id or not student_id:
            continue
        line = OcrLine.query.filter_by(tenant_id=user.tenant_id, batch_id=batch.id, id=line_id).first()
        if not line:
            continue
        line.mapped_student_id = int(student_id)
        line.mapped_status = (entry.get("status") or "present").strip().lower()
        line_updates += 1

    # Commit all lines that have manual mapping.
    lines = OcrLine.query.filter_by(tenant_id=user.tenant_id, batch_id=batch.id).all()
    records = []
    for line in lines:
        if not line.mapped_student_id:
            continue
        records.append(
            {
                "student_id": line.mapped_student_id,
                "status": line.mapped_status or "present",
                "remarks": "ocr_import",
            }
        )

    if not records:
        return fail("No mapped OCR lines to commit")

    try:
        upsert_records(user.tenant_id, int(payload["session_id"]), records)
    except ValueError as exc:
        return fail(str(exc), status=404, code="not_found")

    batch.parse_status = "committed"
    db.session.commit()
    return ok(
        {
            "batch_id": batch.id,
            "session_id": int(payload["session_id"]),
            "line_updates": line_updates,
            "committed_records": len(records),
            "status": batch.parse_status,
        }
    )


@bp.get("/attendance/reports")
@role_required("admin", "teacher")
def api_attendance_reports():
    user = current_user()
    class_id = request.args.get("class_id", type=int)
    student_id = request.args.get("student_id", type=int)
    session_id = request.args.get("session_id", type=int)
    status = request.args.get("status")
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))

    query = AttendanceRecord.query.filter_by(tenant_id=user.tenant_id)
    query = query.join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
    if class_id:
        query = query.filter(AttendanceSession.class_id == class_id)
    if student_id:
        query = query.filter(AttendanceRecord.student_id == student_id)
    if session_id:
        query = query.filter(AttendanceRecord.session_id == session_id)
    if status:
        query = query.filter(AttendanceRecord.status == status)
    if date_from:
        query = query.filter(AttendanceSession.session_date >= date_from)
    if date_to:
        query = query.filter(AttendanceSession.session_date <= date_to)

    rows = query.limit(500).all()
    return ok(
        [
            {
                "id": r.id,
                "session_id": r.session_id,
                "student_id": r.student_id,
                "status": r.status,
                "remarks": r.remarks,
                "session_date": r.session.session_date.isoformat() if r.session else None,
                "class_id": r.session.class_id if r.session else None,
                "section_id": r.session.section_id if r.session else None,
            }
            for r in rows
        ]
    )


@bp.get("/attendance/students/<int:student_id>/summary")
@role_required("admin", "teacher", "parent", "student")
def api_attendance_student_summary(student_id: int):
    user = current_user()
    if not _is_student_in_scope(user, student_id):
        return fail("Forbidden", status=403, code="forbidden")

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    return ok(_attendance_summary_for_student(user.tenant_id, student_id, date_from, date_to))


@bp.get("/attendance/my-summary")
@role_required("parent", "student")
def api_attendance_my_summary():
    user = current_user()
    student_ids = _allowed_student_ids_for_user(user) or []
    if not student_ids:
        return ok([])

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    data = [_attendance_summary_for_student(user.tenant_id, sid, date_from, date_to) for sid in student_ids]
    return ok(data)


@bp.get("/attendance/my-records")
@role_required("parent", "student")
def api_attendance_my_records():
    user = current_user()
    student_ids = _allowed_student_ids_for_user(user) or []
    if not student_ids:
        return ok([])

    requested_student_id = request.args.get("student_id", type=int)
    if requested_student_id:
        if requested_student_id not in student_ids:
            return fail("Forbidden", status=403, code="forbidden")
        student_ids = [requested_student_id]

    query = AttendanceRecord.query.join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id).filter(
        AttendanceRecord.tenant_id == user.tenant_id,
        AttendanceRecord.student_id.in_(student_ids),
    )
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))
    if date_from:
        query = query.filter(AttendanceSession.session_date >= date_from)
    if date_to:
        query = query.filter(AttendanceSession.session_date <= date_to)

    rows = query.order_by(AttendanceSession.session_date.desc()).limit(400).all()
    names = {
        row.id: row.full_name
        for row in Student.query.filter(Student.tenant_id == user.tenant_id, Student.id.in_(student_ids)).all()
    }
    return ok(
        [
            {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": names.get(row.student_id, f"Student-{row.student_id}"),
                "session_id": row.session_id,
                "session_date": row.session.session_date.isoformat() if row.session else None,
                "status": row.status,
                "remarks": row.remarks,
            }
            for row in rows
        ]
    )


@bp.post("/exams")
@role_required("admin", "teacher")
def api_exam_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["name", "class_id"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    exam = create_exam(user.tenant_id, payload["name"], payload["class_id"])
    return ok(_serialize(exam, ["id", "name", "class_id", "status"]))


@bp.get("/exams")
@role_required("admin", "teacher", "parent", "student")
def api_exam_list():
    user = current_user()
    query = Exam.query.filter_by(tenant_id=user.tenant_id)
    class_ids = _allowed_class_ids_for_user(user)
    if class_ids is not None:
        if not class_ids:
            return ok([])
        query = query.filter(Exam.class_id.in_(class_ids))

    rows = query.order_by(Exam.created_at.desc()).limit(200).all()
    return ok([_serialize(x, ["id", "name", "class_id", "status", "scheduled_from", "scheduled_to"]) for x in rows])


@bp.get("/exams/<int:exam_id>/overview")
@role_required("admin", "teacher", "parent", "student")
def api_exam_overview(exam_id: int):
    user = current_user()
    exam = Exam.query.filter_by(tenant_id=user.tenant_id, id=exam_id).first()
    if not exam:
        return fail("Exam not found", status=404, code="not_found")
    if not _is_exam_in_scope(user, exam):
        return fail("Forbidden", status=403, code="forbidden")

    subjects_count = ExamSubject.query.filter_by(tenant_id=user.tenant_id, exam_id=exam.id).count()
    marks_count = (
        db.session.query(Mark)
        .join(ExamSubject, Mark.exam_subject_id == ExamSubject.id)
        .filter(Mark.tenant_id == user.tenant_id, ExamSubject.exam_id == exam.id)
        .count()
    )
    students_covered = (
        db.session.query(Mark.student_id)
        .join(ExamSubject, Mark.exam_subject_id == ExamSubject.id)
        .filter(Mark.tenant_id == user.tenant_id, ExamSubject.exam_id == exam.id)
        .distinct()
        .count()
    )
    return ok(
        {
            "id": exam.id,
            "name": exam.name,
            "class_id": exam.class_id,
            "status": exam.status,
            "scheduled_from": exam.scheduled_from.isoformat() if exam.scheduled_from else None,
            "scheduled_to": exam.scheduled_to.isoformat() if exam.scheduled_to else None,
            "subjects_count": subjects_count,
            "marks_entries_count": marks_count,
            "students_covered": students_covered,
        }
    )


@bp.get("/exams/<int:exam_id>/marks")
@role_required("admin", "teacher", "parent", "student")
def api_exam_marks_list(exam_id: int):
    user = current_user()
    exam = Exam.query.filter_by(tenant_id=user.tenant_id, id=exam_id).first()
    if not exam:
        return fail("Exam not found", status=404, code="not_found")
    if not _is_exam_in_scope(user, exam):
        return fail("Forbidden", status=403, code="forbidden")

    requested_student_id = request.args.get("student_id", type=int)
    allowed_students = _allowed_student_ids_for_user(user)

    query = (
        db.session.query(Mark, ExamSubject)
        .join(ExamSubject, Mark.exam_subject_id == ExamSubject.id)
        .filter(
            Mark.tenant_id == user.tenant_id,
            ExamSubject.tenant_id == user.tenant_id,
            ExamSubject.exam_id == exam.id,
        )
    )

    if requested_student_id:
        if allowed_students is not None and requested_student_id not in set(allowed_students):
            return fail("Forbidden", status=403, code="forbidden")
        query = query.filter(Mark.student_id == requested_student_id)
    elif allowed_students is not None:
        if not allowed_students:
            return ok([])
        query = query.filter(Mark.student_id.in_(allowed_students))

    rows = query.order_by(Mark.student_id.asc(), Mark.id.asc()).limit(1000).all()
    if not rows:
        return ok([])

    student_ids = sorted({mark.student_id for mark, _subject in rows})
    subject_ids = sorted({subject.subject_id for _mark, subject in rows})
    student_map = {
        row.id: row.full_name
        for row in Student.query.filter(Student.tenant_id == user.tenant_id, Student.id.in_(student_ids)).all()
    }
    subject_map = {
        row.id: row.name
        for row in Subject.query.filter(Subject.tenant_id == user.tenant_id, Subject.id.in_(subject_ids)).all()
    }

    return ok(
        [
            {
                "mark_id": mark.id,
                "exam_id": exam.id,
                "student_id": mark.student_id,
                "student_name": student_map.get(mark.student_id, f"Student-{mark.student_id}"),
                "subject_id": exam_subject.subject_id,
                "subject_name": subject_map.get(exam_subject.subject_id, f"Subject-{exam_subject.subject_id}"),
                "marks_obtained": mark.marks_obtained,
                "max_marks": exam_subject.max_marks,
                "grade": mark.grade,
            }
            for mark, exam_subject in rows
        ]
    )


@bp.post("/exams/<int:exam_id>/schedule")
@role_required("admin", "teacher")
def api_exam_schedule(exam_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["scheduled_from", "scheduled_to"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    exam = db.session.get(Exam, exam_id)
    if not exam:
        return fail("Exam not found", status=404, code="not_found")
    exam = schedule_exam(exam, date.fromisoformat(payload["scheduled_from"]), date.fromisoformat(payload["scheduled_to"]))
    return ok(_serialize(exam, ["id", "status", "scheduled_from", "scheduled_to"]))


@bp.post("/exams/<int:exam_id>/marks")
@role_required("admin", "teacher")
def api_exam_marks(exam_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["subject_id", "entries"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    subject = add_marks(user.tenant_id, exam_id, payload["subject_id"], payload["entries"])
    return ok(_serialize(subject, ["id", "exam_id", "subject_id", "max_marks"]))


@bp.post("/exams/<int:exam_id>/publish")
@role_required("admin", "teacher")
def api_exam_publish(exam_id: int):
    user = current_user()
    cards = publish_report_cards(user.tenant_id, exam_id)
    return ok({"exam_id": exam_id, "published_report_cards": len(cards)})


@bp.get("/exams/my-results")
@role_required("parent", "student")
def api_exam_my_results():
    user = current_user()
    student_ids = _allowed_student_ids_for_user(user) or []
    if not student_ids:
        return ok([])

    query = ReportCard.query.filter(
        ReportCard.tenant_id == user.tenant_id,
        ReportCard.student_id.in_(student_ids),
    )
    rows = query.order_by(ReportCard.created_at.desc()).limit(100).all()
    if not rows:
        return ok([])

    student_map = {
        row.id: row.full_name
        for row in Student.query.filter(Student.tenant_id == user.tenant_id, Student.id.in_(student_ids)).all()
    }
    exam_ids = sorted({row.exam_id for row in rows})
    exam_map = {row.id: row.name for row in Exam.query.filter(Exam.tenant_id == user.tenant_id, Exam.id.in_(exam_ids)).all()}
    return ok(
        [
            {
                "report_card_id": row.id,
                "student_id": row.student_id,
                "student_name": student_map.get(row.student_id, f"Student-{row.student_id}"),
                "exam_id": row.exam_id,
                "exam_name": exam_map.get(row.exam_id, f"Exam-{row.exam_id}"),
                "status": row.status,
                "total_marks": row.total_marks,
                "percentage": row.percentage,
                "published_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    )


@bp.get("/report-cards")
@role_required("admin", "teacher", "parent", "student")
def api_report_cards_list():
    user = current_user()
    exam_id = request.args.get("exam_id", type=int)
    student_id = request.args.get("student_id", type=int)

    query = ReportCard.query.filter_by(tenant_id=user.tenant_id)
    allowed_students = _allowed_student_ids_for_user(user)

    if student_id:
        if allowed_students is not None and student_id not in set(allowed_students):
            return fail("Forbidden", status=403, code="forbidden")
        query = query.filter(ReportCard.student_id == student_id)
    elif allowed_students is not None:
        if not allowed_students:
            return ok([])
        query = query.filter(ReportCard.student_id.in_(allowed_students))

    if exam_id:
        query = query.filter(ReportCard.exam_id == exam_id)

    rows = query.order_by(ReportCard.created_at.desc()).limit(200).all()
    if not rows:
        return ok([])

    student_ids = sorted({row.student_id for row in rows})
    exam_ids = sorted({row.exam_id for row in rows})
    student_map = {
        row.id: row.full_name
        for row in Student.query.filter(Student.tenant_id == user.tenant_id, Student.id.in_(student_ids)).all()
    }
    exam_map = {row.id: row.name for row in Exam.query.filter(Exam.tenant_id == user.tenant_id, Exam.id.in_(exam_ids)).all()}

    return ok(
        [
            {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": student_map.get(row.student_id, f"Student-{row.student_id}"),
                "exam_id": row.exam_id,
                "exam_name": exam_map.get(row.exam_id, f"Exam-{row.exam_id}"),
                "total_marks": row.total_marks,
                "percentage": row.percentage,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    )


@bp.get("/report-cards/<int:student_id>")
@role_required("admin", "teacher", "parent", "student")
def api_report_card(student_id: int):
    user = current_user()
    if not _is_student_in_scope(user, student_id):
        return fail("Forbidden", status=403, code="forbidden")
    card = (
        ReportCard.query.filter_by(tenant_id=user.tenant_id, student_id=student_id)
        .order_by(ReportCard.created_at.desc())
        .first()
    )
    if not card:
        return fail("Report card not found", status=404, code="not_found")

    data = {
        "id": card.id,
        "student_id": card.student_id,
        "exam_id": card.exam_id,
        "total_marks": card.total_marks,
        "percentage": card.percentage,
        "status": card.status,
        "items": [],
    }

    for item in card.items:
        subject = db.session.get(Subject, item.subject_id)
        data["items"].append(
            {
                "subject": subject.name if subject else f"Subject-{item.subject_id}",
                "marks_obtained": item.marks_obtained,
                "max_marks": item.max_marks,
                "grade": item.grade,
            }
        )

    return ok(data)


@bp.get("/report-cards/<int:student_id>/pdf")
@role_required("admin", "teacher", "parent", "student")
def api_report_card_pdf(student_id: int):
    user = current_user()
    if not _is_student_in_scope(user, student_id):
        return fail("Forbidden", status=403, code="forbidden")
    card = (
        ReportCard.query.filter_by(tenant_id=user.tenant_id, student_id=student_id)
        .order_by(ReportCard.created_at.desc())
        .first()
    )
    if not card:
        return fail("Report card not found", status=404, code="not_found")

    student = db.session.get(Student, student_id)
    exam = db.session.get(Exam, card.exam_id)
    items = []
    for item in card.items:
        subject = db.session.get(Subject, item.subject_id)
        items.append(
            {
                "subject": subject.name if subject else f"Subject-{item.subject_id}",
                "marks_obtained": item.marks_obtained,
                "max_marks": item.max_marks,
                "grade": item.grade,
            }
        )

    payload = render_report_card_pdf(
        student_name=student.full_name if student else f"Student-{student_id}",
        exam_name=exam.name if exam else "Exam",
        items=items,
        total=card.total_marks,
        percentage=card.percentage,
    )

    from io import BytesIO

    return send_file(
        BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"report_card_{student_id}.pdf",
    )


@bp.post("/fees/structures")
@role_required("admin")
def api_fee_structure_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["class_id", "title", "total_amount"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    obj = create_structure(user.tenant_id, payload["class_id"], payload["title"], payload["total_amount"])
    return ok(_serialize(obj, ["id", "class_id", "title", "total_amount"]))


@bp.get("/fees/structures")
@role_required("admin", "teacher")
def api_fee_structure_list():
    user = current_user()
    rows = FeeStructure.query.filter_by(tenant_id=user.tenant_id).order_by(FeeStructure.created_at.desc()).limit(200).all()
    return ok([_serialize(x, ["id", "class_id", "title", "total_amount"]) for x in rows])


@bp.post("/fees/installments")
@role_required("admin")
def api_fee_installment_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["structure_id", "title", "amount", "due_date"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    obj = create_installment(
        user.tenant_id,
        payload["structure_id"],
        payload["title"],
        payload["amount"],
        date.fromisoformat(payload["due_date"]),
    )
    return ok(_serialize(obj, ["id", "structure_id", "title", "amount", "due_date"]))


@bp.get("/fees/installments")
@role_required("admin", "teacher")
def api_fee_installment_list():
    user = current_user()
    structure_id = request.args.get("structure_id", type=int)
    query = FeeInstallment.query.filter_by(tenant_id=user.tenant_id)
    if structure_id:
        query = query.filter(FeeInstallment.structure_id == structure_id)
    rows = query.order_by(FeeInstallment.due_date.asc()).limit(500).all()
    return ok([_serialize(x, ["id", "structure_id", "title", "amount", "due_date"]) for x in rows])


@bp.post("/fees/receipts")
@role_required("admin")
def api_fee_receipt_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["ledger_id", "amount"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    try:
        receipt = create_receipt(
            user.tenant_id,
            payload["ledger_id"],
            payload["amount"],
            payload.get("payment_mode", "cash"),
            payload.get("reference_no"),
        )
    except ValueError as exc:
        return fail(str(exc), status=404, code="not_found")
    return ok(_serialize(receipt, ["id", "ledger_id", "amount", "payment_mode", "reference_no"]))


@bp.get("/fees/<int:student_id>/ledger")
@role_required("admin", "teacher", "parent", "student")
def api_fee_ledger(student_id: int):
    user = current_user()
    if not _is_student_in_scope(user, student_id):
        return fail("Forbidden", status=403, code="forbidden")
    ledgers = ledgers_for_student(user.tenant_id, student_id)
    return ok(
        [
            {
                "id": l.id,
                "installment_id": l.installment_id,
                "amount_due": l.amount_due,
                "amount_paid": l.amount_paid,
                "status": l.status,
            }
            for l in ledgers
        ]
    )


@bp.get("/fees/<int:student_id>/dues")
@role_required("admin", "teacher", "parent", "student")
def api_fee_dues(student_id: int):
    user = current_user()
    if not _is_student_in_scope(user, student_id):
        return fail("Forbidden", status=403, code="forbidden")
    ledgers = ledgers_for_student(user.tenant_id, student_id)
    due = sum(max(l.amount_due - l.amount_paid, 0) for l in ledgers)
    return ok({"student_id": student_id, "outstanding_due": due})


@bp.post("/notices")
@role_required("admin", "teacher")
def api_notice_create():
    user = current_user()
    upload = request.files.get("file")
    payload = request.form.to_dict() if upload else (request.get_json(silent=True) or {})

    valid, missing = require_fields(payload, ["title", "body"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    notice = create_notice(
        tenant_id=user.tenant_id,
        title=payload["title"],
        body=payload["body"],
        posted_by=user.id,
        audience=payload.get("audience", "all"),
    )

    if upload:
        media_type = payload.get("media_type", "file")
        safe_name = f"{uuid4().hex}_{upload.filename}"
        target = Path(current_app.config["UPLOAD_FOLDER"]) / safe_name
        upload.save(target)
        attach_notice_media(user.tenant_id, notice.id, media_type, str(target))

    return ok(_serialize(notice, ["id", "title", "body", "audience", "posted_by"]))


@bp.get("/notices")
@role_required("admin", "teacher", "parent", "student")
def api_notice_list():
    user = current_user()
    raw = Notice.query.filter_by(tenant_id=user.tenant_id).order_by(Notice.created_at.desc()).limit(200).all()
    notices = [row for row in raw if _notice_visible_to_user(user, row)]
    return ok(
        [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "audience": n.audience,
                "created_at": n.created_at.isoformat(),
                "media": [
                    {
                        "id": m.id,
                        "media_type": m.media_type,
                        "file_path": m.file_path,
                    }
                    for m in n.media_items
                ],
            }
            for n in notices
        ]
    )


@bp.post("/events")
@role_required("admin", "teacher")
def api_event_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["title", "starts_at"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    event = create_event(
        user.tenant_id,
        payload["title"],
        payload.get("details", ""),
        datetime.fromisoformat(payload["starts_at"]),
        datetime.fromisoformat(payload["ends_at"]) if payload.get("ends_at") else None,
        payload.get("event_type", "school"),
    )
    return ok(_serialize(event, ["id", "title", "details", "starts_at", "ends_at", "event_type"]))


@bp.get("/events")
@role_required("admin", "teacher", "parent", "student")
def api_event_list():
    user = current_user()
    rows = Event.query.filter_by(tenant_id=user.tenant_id).order_by(Event.starts_at.asc()).limit(200).all()
    return ok([_serialize(x, ["id", "title", "details", "starts_at", "ends_at", "event_type"]) for x in rows])


@bp.post("/reminders")
@role_required("admin", "teacher")
def api_reminder_create():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["title", "remind_at"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    reminder = create_reminder(
        user.tenant_id,
        payload["title"],
        payload.get("content", ""),
        datetime.fromisoformat(payload["remind_at"]),
        user.id,
    )
    return ok(_serialize(reminder, ["id", "title", "content", "remind_at", "created_by"]))


@bp.get("/reminders")
@role_required("admin", "teacher", "parent", "student")
def api_reminder_list():
    user = current_user()
    query = Reminder.query.filter_by(tenant_id=user.tenant_id)
    creator_ids = _visible_reminder_creator_ids(user)
    if creator_ids is not None:
        query = query.filter(Reminder.created_by.in_(creator_ids))
    rows = query.order_by(Reminder.remind_at.asc()).limit(300).all()
    return ok([_serialize(x, ["id", "title", "content", "remind_at", "created_by"]) for x in rows])


@bp.get("/calendar")
@role_required("admin", "teacher", "parent", "student")
def api_calendar_list():
    user = current_user()
    rows = CalendarEntry.query.filter_by(tenant_id=user.tenant_id).order_by(CalendarEntry.starts_at.asc()).limit(300).all()
    creator_ids = _visible_reminder_creator_ids(user)
    allowed_reminder_ids: set[int] | None = None
    if creator_ids is not None:
        allowed_reminder_ids = {
            row.id
            for row in Reminder.query.filter(
                Reminder.tenant_id == user.tenant_id,
                Reminder.created_by.in_(creator_ids),
            ).all()
        }

    filtered = []
    for row in rows:
        if row.entry_type != "reminder":
            filtered.append(row)
            continue
        if allowed_reminder_ids is None:
            filtered.append(row)
            continue
        if row.reference_type == "reminder" and row.reference_id in allowed_reminder_ids:
            filtered.append(row)

    return ok([_serialize(x, ["id", "title", "starts_at", "ends_at", "entry_type", "reference_type", "reference_id"]) for x in filtered])


@bp.post("/messages/threads")
@role_required("admin", "teacher", "parent", "student")
def api_thread_create():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload.get("member_ids"), str):
        payload["member_ids"] = _parse_csv_ints(payload.get("member_ids"))

    valid, missing = require_fields(payload, ["thread_type", "member_ids"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    member_ids = payload.get("member_ids", [])
    if not isinstance(member_ids, list) or not member_ids:
        return fail("member_ids must be a non-empty list")

    user = current_user()
    existing_user_ids = {
        row.id
        for row in User.query.filter(User.tenant_id == user.tenant_id, User.id.in_(member_ids)).all()
    }
    missing_user_ids = sorted(set(member_ids) - existing_user_ids)
    if missing_user_ids:
        return fail("Some member_ids are invalid", details={"missing_user_ids": missing_user_ids})

    thread = create_thread(
        tenant_id=user.tenant_id,
        title=payload.get("title", ""),
        thread_type=payload["thread_type"],
        created_by=user.id,
        member_ids=member_ids,
    )
    return ok(_serialize(thread, ["id", "title", "thread_type", "created_by"]))


@bp.get("/messages/threads")
@role_required("admin", "teacher", "parent", "student")
def api_thread_list():
    user = current_user()
    rows = (
        Thread.query.join(ThreadMember, ThreadMember.thread_id == Thread.id)
        .filter(Thread.tenant_id == user.tenant_id, ThreadMember.user_id == user.id)
        .order_by(Thread.updated_at.desc())
        .limit(200)
        .all()
    )
    return ok([_serialize(x, ["id", "title", "thread_type", "created_by", "created_at", "updated_at"]) for x in rows])


@bp.post("/messages/threads/<int:thread_id>/messages")
@role_required("admin", "teacher", "parent", "student")
def api_message_post(thread_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["body"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    if not _thread_member_exists(user.tenant_id, thread_id, user.id):
        return fail("Forbidden", status=403, code="forbidden")

    message = post_message(user.tenant_id, thread_id, user.id, payload["body"])
    return ok(_serialize(message, ["id", "thread_id", "sender_id", "body", "created_at"]))


@bp.get("/messages/threads/<int:thread_id>/messages")
@role_required("admin", "teacher", "parent", "student")
def api_message_list(thread_id: int):
    user = current_user()
    if not _thread_member_exists(user.tenant_id, thread_id, user.id):
        return fail("Forbidden", status=403, code="forbidden")

    since = request.args.get("since")
    query = Message.query.filter_by(tenant_id=user.tenant_id, thread_id=thread_id)
    if since:
        try:
            query = query.filter(Message.created_at > datetime.fromisoformat(since))
        except ValueError:
            return fail("Invalid 'since' timestamp. Use ISO format.")

    rows = query.order_by(Message.created_at.asc()).limit(200).all()
    for row in rows:
        if row.sender_id != user.id:
            mark_read(user.tenant_id, row.id, user.id)

    unread = (
        Message.query.outerjoin(
            MessageRead,
            and_(
                MessageRead.message_id == Message.id,
                MessageRead.user_id == user.id,
            ),
        )
        .filter(
            Message.tenant_id == user.tenant_id,
            Message.thread_id == thread_id,
            Message.sender_id != user.id,
            MessageRead.id.is_(None),
        )
        .count()
    )
    return ok(
        [
            {
                "id": r.id,
                "thread_id": r.thread_id,
                "sender_id": r.sender_id,
                "body": r.body,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        meta={"unread_counter_hint": unread},
    )


@bp.route("/admissions/forms", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_admissions_forms():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["student_name", "guardian_name", "target_class"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("admissions", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "student_name", "guardian_name", "target_class", "status"]))

    rows = list_records("admissions", user.tenant_id)
    return ok([_serialize(x, ["id", "student_name", "guardian_name", "target_class", "status"]) for x in rows])


@bp.patch("/admissions/forms/<int:form_id>/status")
@role_required("admin", "teacher")
def api_admissions_status_update(form_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["status"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    form = AdmissionForm.query.filter_by(id=form_id, tenant_id=user.tenant_id).first()
    if not form:
        return fail("Admission form not found", status=404, code="not_found")

    old_status = form.status
    form.status = payload["status"]
    db.session.commit()
    admission_status_update(user.tenant_id, form.id, old_status, form.status, user.id)
    return ok(_serialize(form, ["id", "student_name", "guardian_name", "target_class", "status"]))


@bp.route("/transport/routes", methods=["GET", "POST"])
@role_required("admin")
def api_transport_routes():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["name"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("transport_routes", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "name", "shift"]))
    rows = list_records("transport_routes", user.tenant_id)
    return ok([_serialize(x, ["id", "name", "shift"]) for x in rows])


@bp.route("/transport/vehicles", methods=["GET", "POST"])
@role_required("admin")
def api_transport_vehicles():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["registration_no"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("vehicles", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "registration_no", "capacity"]))
    rows = list_records("vehicles", user.tenant_id)
    return ok([_serialize(x, ["id", "registration_no", "capacity"]) for x in rows])


@bp.route("/transport/stops", methods=["GET", "POST"])
@role_required("admin")
def api_transport_stops():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["route_id", "stop_name", "stop_order"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("route_stops", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "route_id", "stop_name", "stop_order"]))
    rows = list_records("route_stops", user.tenant_id)
    return ok([_serialize(x, ["id", "route_id", "stop_name", "stop_order"]) for x in rows])


@bp.route("/payroll/cycles", methods=["GET", "POST"])
@role_required("admin")
def api_payroll_cycles():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["month_label"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("payroll_cycles", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "month_label", "status"]))
    rows = list_records("payroll_cycles", user.tenant_id)
    return ok([_serialize(x, ["id", "month_label", "status"]) for x in rows])


@bp.route("/payroll/entries", methods=["GET", "POST"])
@role_required("admin")
def api_payroll_entries():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["cycle_id", "teacher_user_id", "gross_pay", "net_pay"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("payroll_entries", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "cycle_id", "teacher_user_id", "gross_pay", "net_pay"]))
    rows = list_records("payroll_entries", user.tenant_id)
    return ok([_serialize(x, ["id", "cycle_id", "teacher_user_id", "gross_pay", "net_pay"]) for x in rows])


@bp.route("/library/books", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_library_books():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["title", "author"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("books", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "title", "author", "isbn"]))
    rows = list_records("books", user.tenant_id)
    return ok([_serialize(x, ["id", "title", "author", "isbn"]) for x in rows])


@bp.route("/library/loans", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_library_loans():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["copy_id", "borrower_user_id", "due_date"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        payload["due_date"] = date.fromisoformat(payload["due_date"])
        obj = create_record("book_loans", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "copy_id", "borrower_user_id", "due_date", "returned_at"]))
    rows = list_records("book_loans", user.tenant_id)
    return ok([_serialize(x, ["id", "copy_id", "borrower_user_id", "due_date", "returned_at"]) for x in rows])


@bp.route("/hostel/rooms", methods=["GET", "POST"])
@role_required("admin")
def api_hostel_rooms():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["hostel_id", "room_no"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("rooms", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "hostel_id", "room_no", "capacity"]))
    rows = Room.query.filter_by(tenant_id=user.tenant_id).all()
    return ok([_serialize(x, ["id", "hostel_id", "room_no", "capacity"]) for x in rows])


@bp.route("/hostel/hostels", methods=["GET", "POST"])
@role_required("admin")
def api_hostels():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["name"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("hostels", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "name"]))
    rows = list_records("hostels", user.tenant_id)
    return ok([_serialize(x, ["id", "name"]) for x in rows])


@bp.route("/inventory/items", methods=["GET", "POST"])
@role_required("admin")
def api_inventory_items():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["name"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("inventory_items", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "name", "sku", "quantity"]))
    rows = list_records("inventory_items", user.tenant_id)
    return ok([_serialize(x, ["id", "name", "sku", "quantity"]) for x in rows])


@bp.route("/inventory/stock-moves", methods=["GET", "POST"])
@role_required("admin")
def api_inventory_stock_moves():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["item_id", "move_type", "quantity"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("stock_moves", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "item_id", "move_type", "quantity", "notes"]))
    rows = list_records("stock_moves", user.tenant_id)
    return ok([_serialize(x, ["id", "item_id", "move_type", "quantity", "notes"]) for x in rows])


@bp.route("/coaching/courses", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_coaching_courses():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["code", "title"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("courses", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "code", "title"]))
    rows = list_records("courses", user.tenant_id)
    return ok([_serialize(x, ["id", "code", "title"]) for x in rows])


@bp.route("/coaching/batches", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_coaching_batches():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["course_id", "name"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("coaching_batches", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "course_id", "name", "timing"]))
    rows = list_records("coaching_batches", user.tenant_id)
    return ok([_serialize(x, ["id", "course_id", "name", "timing"]) for x in rows])


@bp.route("/coaching/test-series", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_coaching_test_series():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["batch_id", "title"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("test_series", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "batch_id", "title", "total_marks"]))
    rows = list_records("test_series", user.tenant_id)
    return ok([_serialize(x, ["id", "batch_id", "title", "total_marks"]) for x in rows])


@bp.route("/coaching/test-attempts", methods=["GET", "POST"])
@role_required("admin", "teacher")
def api_coaching_test_attempts():
    user = current_user()
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        valid, missing = require_fields(payload, ["test_series_id", "student_id", "score"])
        if not valid:
            return fail("Missing required fields", details={"missing": missing})
        obj = create_record("test_attempts", user.tenant_id, payload)
        return ok(_serialize(obj, ["id", "test_series_id", "student_id", "score"]))
    rows = list_records("test_attempts", user.tenant_id)
    return ok([_serialize(x, ["id", "test_series_id", "student_id", "score"]) for x in rows])


@bp.post("/ai/chat")
@role_required("admin", "teacher", "parent", "student")
def api_ai_chat():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["prompt"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    role = user.roles[0].name.lower() if user.roles else "student"
    conversation, text, routed_action = ask_ai(
        user.tenant_id,
        user.id,
        role,
        payload["prompt"],
        enable_routing=not bool(payload.get("action_type")),
    )

    if payload.get("action_type"):
        request_obj, state = queue_or_execute_action(
            tenant_id=user.tenant_id,
            requested_by=user.id,
            action_type=payload["action_type"],
            payload=payload.get("action_payload", {}),
        )
        return ok(
            {
                "conversation_id": conversation.id,
                "assistant_response": text,
                "action": {
                    "id": request_obj.id,
                    "action_type": request_obj.action_type,
                    "risk": request_obj.risk,
                    "status": state,
                },
            }
        )

    response = {"conversation_id": conversation.id, "assistant_response": text}
    if routed_action:
        response["action"] = routed_action
    return ok(response)


@bp.get("/ai/actions/pending")
@role_required("admin", "teacher")
def api_ai_pending_actions():
    user = current_user()
    rows = pending_actions(user.tenant_id)
    return ok(
        [
            {
                "id": row.id,
                "action_type": row.action_type,
                "risk": row.risk,
                "payload": row.payload_json,
                "status": row.status,
            }
            for row in rows
        ]
    )


@bp.post("/ai/actions/<int:action_id>/approve")
@role_required("admin", "teacher")
def api_ai_approve(action_id: int):
    user = current_user()
    payload = request.get_json(silent=True) or {}
    obj = decide_action(user.tenant_id, action_id, user.id, "approve", payload.get("comment"))
    return ok({"id": obj.id, "status": obj.status})


@bp.post("/ai/actions/<int:action_id>/reject")
@role_required("admin", "teacher")
def api_ai_reject(action_id: int):
    user = current_user()
    payload = request.get_json(silent=True) or {}
    obj = decide_action(user.tenant_id, action_id, user.id, "reject", payload.get("comment"))
    return ok({"id": obj.id, "status": obj.status})


@bp.get("/meta/types")
def api_types():
    return ok(
        {
            "UserRole": ["admin", "teacher", "parent", "student"],
            "NoticeMediaType": ["text", "audio", "video", "file"],
            "AttendanceSource": ["manual", "ocr"],
            "FeeStatus": ["paid", "partial", "overdue", "waived"],
            "ThreadType": ["dm", "group", "class"],
            "AIActionRisk": ["low", "medium", "high"],
            "AIApprovalStatus": ["pending", "approved", "rejected", "executed"],
        }
    )
