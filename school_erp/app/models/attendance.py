from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class AttendanceSession(BaseModel, TenantMixin):
    __tablename__ = "attendance_sessions"

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)
    session_date = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(20), nullable=False, default="manual")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class AttendanceRecord(BaseModel, TenantMixin):
    __tablename__ = "attendance_records"

    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="present")
    remarks = db.Column(db.String(255), nullable=True)

    session = db.relationship("AttendanceSession", backref="records")
    student = db.relationship("Student", backref="attendance_records")

    __table_args__ = (db.UniqueConstraint("session_id", "student_id", name="uq_attendance_student"),)


class TeacherAttendance(BaseModel, TenantMixin):
    __tablename__ = "teacher_attendance"

    teacher_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="present")


class OcrImportBatch(BaseModel, TenantMixin):
    __tablename__ = "ocr_import_batches"

    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    parse_status = db.Column(db.String(20), nullable=False, default="pending")
    notes = db.Column(db.String(255), nullable=True)


class OcrLine(BaseModel, TenantMixin):
    __tablename__ = "ocr_lines"

    batch_id = db.Column(db.Integer, db.ForeignKey("ocr_import_batches.id"), nullable=False)
    raw_text = db.Column(db.Text, nullable=False)
    mapped_student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    mapped_status = db.Column(db.String(20), nullable=True)

    batch = db.relationship("OcrImportBatch", backref="lines")
