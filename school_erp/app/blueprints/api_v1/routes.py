from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from flask import current_app, request, send_file

from app.blueprints.api_v1 import bp
from app.core.auth import current_user
from app.core.rbac import role_required
from app.core.responses import fail, ok
from app.core.validators import require_fields
from app.extensions import db
from app.models.academic import Classroom, Section, Student, Subject
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.communication import CalendarEntry, Event, Message, Notice, Reminder, Thread, ThreadMember
from app.models.enterprise import AdmissionForm, Room
from app.models.exams import Exam, ReportCard
from app.models.finance import FeeInstallment, FeeLedger, FeeStructure
from app.models.identity import User
from app.services.ai_service import ask_ai, decide_action, pending_actions, queue_or_execute_action
from app.services.attendance_service import create_ocr_batch, create_session, mark_teacher_self, upsert_records
from app.services.communication_service import attach_notice_media, create_event, create_notice, create_reminder
from app.services.dashboard_service import dashboard_summary
from app.services.enterprise_service import admission_status_update, create_record, list_records
from app.services.exam_service import add_marks, create_exam, publish_report_cards, schedule_exam
from app.services.fees_service import create_installment, create_receipt, create_structure, ledgers_for_student
from app.services.messaging_service import create_thread, post_message
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


@bp.get("/health")
def health():
    return ok({"status": "ok", "service": "school-erp-api"})


@bp.get("/dashboard/<role>")
@role_required("admin", "teacher", "parent", "student")
def api_dashboard(role: str):
    user = current_user()
    return ok(dashboard_summary(user.tenant_id, role))


@bp.get("/directory/classes")
@role_required("admin", "teacher", "parent", "student")
def api_directory_classes():
    user = current_user()
    classes = Classroom.query.filter_by(tenant_id=user.tenant_id).order_by(Classroom.name.asc()).all()
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
    rows = Student.query.filter_by(tenant_id=user.tenant_id).order_by(Student.full_name.asc()).limit(500).all()
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
        query = query.filter((User.id == user.id) | (User.username == "teacher"))

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
    upsert_records(user.tenant_id, session_id, records)
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


@bp.get("/attendance/reports")
@role_required("admin", "teacher")
def api_attendance_reports():
    user = current_user()
    class_id = request.args.get("class_id", type=int)
    query = AttendanceRecord.query.filter_by(tenant_id=user.tenant_id)
    if class_id:
        query = query.join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id).filter(
            AttendanceSession.class_id == class_id
        )
    rows = query.limit(500).all()
    return ok(
        [
            {
                "id": r.id,
                "session_id": r.session_id,
                "student_id": r.student_id,
                "status": r.status,
            }
            for r in rows
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
    rows = Exam.query.filter_by(tenant_id=user.tenant_id).order_by(Exam.created_at.desc()).limit(200).all()
    return ok([_serialize(x, ["id", "name", "class_id", "status", "scheduled_from", "scheduled_to"]) for x in rows])


@bp.post("/exams/<int:exam_id>/schedule")
@role_required("admin", "teacher")
def api_exam_schedule(exam_id: int):
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["scheduled_from", "scheduled_to"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    exam = Exam.query.get_or_404(exam_id)
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


@bp.get("/report-cards/<int:student_id>")
@role_required("admin", "teacher", "parent", "student")
def api_report_card(student_id: int):
    user = current_user()
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
    notices = Notice.query.filter_by(tenant_id=user.tenant_id).order_by(Notice.created_at.desc()).limit(100).all()
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
    rows = Reminder.query.filter_by(tenant_id=user.tenant_id).order_by(Reminder.remind_at.asc()).limit(300).all()
    return ok([_serialize(x, ["id", "title", "content", "remind_at", "created_by"]) for x in rows])


@bp.get("/calendar")
@role_required("admin", "teacher", "parent", "student")
def api_calendar_list():
    user = current_user()
    rows = CalendarEntry.query.filter_by(tenant_id=user.tenant_id).order_by(CalendarEntry.starts_at.asc()).limit(300).all()
    return ok([_serialize(x, ["id", "title", "starts_at", "ends_at", "entry_type", "reference_type", "reference_id"]) for x in rows])


@bp.post("/messages/threads")
@role_required("admin", "teacher", "parent", "student")
def api_thread_create():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload.get("member_ids"), str):
        payload["member_ids"] = _parse_csv_ints(payload.get("member_ids"))

    valid, missing = require_fields(payload, ["thread_type", "member_ids"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    user = current_user()
    thread = create_thread(
        tenant_id=user.tenant_id,
        title=payload.get("title", ""),
        thread_type=payload["thread_type"],
        created_by=user.id,
        member_ids=payload.get("member_ids", []),
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
    message = post_message(user.tenant_id, thread_id, user.id, payload["body"])
    return ok(_serialize(message, ["id", "thread_id", "sender_id", "body", "created_at"]))


@bp.get("/messages/threads/<int:thread_id>/messages")
@role_required("admin", "teacher", "parent", "student")
def api_message_list(thread_id: int):
    user = current_user()
    since = request.args.get("since")
    query = Message.query.filter_by(tenant_id=user.tenant_id, thread_id=thread_id)
    if since:
        try:
            query = query.filter(Message.created_at > datetime.fromisoformat(since))
        except ValueError:
            return fail("Invalid 'since' timestamp. Use ISO format.")

    rows = query.order_by(Message.created_at.asc()).limit(200).all()
    unread = Message.query.filter_by(tenant_id=user.tenant_id, thread_id=thread_id).count()
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
    conversation, text = ask_ai(user.tenant_id, user.id, role, payload["prompt"])

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

    return ok({"conversation_id": conversation.id, "assistant_response": text})


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
