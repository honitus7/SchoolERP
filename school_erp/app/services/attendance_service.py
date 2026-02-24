from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models.attendance import AttendanceRecord, AttendanceSession, OcrImportBatch, OcrLine, TeacherAttendance


def create_session(tenant_id: int, class_id: int, section_id: int | None, subject_id: int | None, session_date: date, source: str, created_by: int):
    session = AttendanceSession(
        tenant_id=tenant_id,
        class_id=class_id,
        section_id=section_id,
        subject_id=subject_id,
        session_date=session_date,
        source=source,
        created_by=created_by,
    )
    db.session.add(session)
    db.session.commit()
    return session


def upsert_records(tenant_id: int, session_id: int, records: list[dict]):
    session = AttendanceSession.query.filter_by(id=session_id, tenant_id=tenant_id).first()
    if not session:
        raise ValueError("Attendance session not found")

    for item in records:
        student_id = item["student_id"]
        rec = AttendanceRecord.query.filter_by(
            tenant_id=tenant_id,
            session_id=session_id,
            student_id=student_id,
        ).first()
        if not rec:
            rec = AttendanceRecord(
                tenant_id=tenant_id,
                session_id=session_id,
                student_id=student_id,
                status=item.get("status", "present"),
                remarks=item.get("remarks"),
            )
            db.session.add(rec)
        else:
            rec.status = item.get("status", rec.status)
            rec.remarks = item.get("remarks", rec.remarks)
    db.session.commit()


def mark_teacher_self(tenant_id: int, teacher_user_id: int, attendance_date: date, status: str):
    record = TeacherAttendance.query.filter_by(
        tenant_id=tenant_id,
        teacher_user_id=teacher_user_id,
        attendance_date=attendance_date,
    ).first()
    if not record:
        record = TeacherAttendance(
            tenant_id=tenant_id,
            teacher_user_id=teacher_user_id,
            attendance_date=attendance_date,
            status=status,
        )
        db.session.add(record)
    else:
        record.status = status
    db.session.commit()
    return record


def create_ocr_batch(tenant_id: int, uploaded_by: int, file_path: str, extracted_lines: list[str]):
    batch = OcrImportBatch(
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        file_path=file_path,
        parse_status="review",
    )
    db.session.add(batch)
    db.session.flush()

    for line in extracted_lines:
        db.session.add(
            OcrLine(
                tenant_id=tenant_id,
                batch_id=batch.id,
                raw_text=line,
            )
        )

    db.session.commit()
    return batch
