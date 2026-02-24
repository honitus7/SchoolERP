from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class Exam(BaseModel, TenantMixin):
    __tablename__ = "exams"

    name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    scheduled_from = db.Column(db.Date, nullable=True)
    scheduled_to = db.Column(db.Date, nullable=True)


class ExamSubject(BaseModel, TenantMixin):
    __tablename__ = "exam_subjects"

    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    exam_date = db.Column(db.Date, nullable=True)
    max_marks = db.Column(db.Float, nullable=False, default=100)

    exam = db.relationship("Exam", backref="exam_subjects")


class Mark(BaseModel, TenantMixin):
    __tablename__ = "marks"

    exam_subject_id = db.Column(db.Integer, db.ForeignKey("exam_subjects.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(10), nullable=True)

    exam_subject = db.relationship("ExamSubject", backref="marks")


class GradeScale(BaseModel, TenantMixin):
    __tablename__ = "grade_scales"

    grade = db.Column(db.String(10), nullable=False)
    min_percentage = db.Column(db.Float, nullable=False)
    max_percentage = db.Column(db.Float, nullable=False)


class ReportCard(BaseModel, TenantMixin):
    __tablename__ = "report_cards"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    total_marks = db.Column(db.Float, nullable=False, default=0)
    percentage = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="published")

    student = db.relationship("Student", backref="report_cards")
    exam = db.relationship("Exam", backref="report_cards")


class ReportCardItem(BaseModel, TenantMixin):
    __tablename__ = "report_card_items"

    report_card_id = db.Column(db.Integer, db.ForeignKey("report_cards.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(10), nullable=True)

    report_card = db.relationship("ReportCard", backref="items")
