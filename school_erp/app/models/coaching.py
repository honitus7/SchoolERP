from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class Course(BaseModel, TenantMixin):
    __tablename__ = "courses"

    code = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(120), nullable=False)


class CoachingBatch(BaseModel, TenantMixin):
    __tablename__ = "coaching_batches"

    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    timing = db.Column(db.String(80), nullable=True)


class TestSeries(BaseModel, TenantMixin):
    __tablename__ = "test_series"

    batch_id = db.Column(db.Integer, db.ForeignKey("coaching_batches.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    total_marks = db.Column(db.Float, nullable=False, default=100)


class TestAttempt(BaseModel, TenantMixin):
    __tablename__ = "test_attempts"

    test_series_id = db.Column(db.Integer, db.ForeignKey("test_series.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    score = db.Column(db.Float, nullable=False)
