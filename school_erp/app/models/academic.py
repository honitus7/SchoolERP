from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class Classroom(BaseModel, TenantMixin):
    __tablename__ = "classes"

    name = db.Column(db.String(60), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)


class Section(BaseModel, TenantMixin):
    __tablename__ = "sections"

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name = db.Column(db.String(30), nullable=False)

    classroom = db.relationship("Classroom", backref="sections")


class Subject(BaseModel, TenantMixin):
    __tablename__ = "subjects"

    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)


class Batch(BaseModel, TenantMixin):
    __tablename__ = "batches"

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    name = db.Column(db.String(120), nullable=False)
    schedule = db.Column(db.String(120), nullable=True)

    classroom = db.relationship("Classroom", backref="batches")


class Student(BaseModel, TenantMixin):
    __tablename__ = "students"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    admission_no = db.Column(db.String(40), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=True)
    dob = db.Column(db.Date, nullable=True)

    user = db.relationship("User", backref="student_profile", uselist=False)
    classroom = db.relationship("Classroom", backref="students")
    section = db.relationship("Section", backref="students")

    __table_args__ = (db.UniqueConstraint("tenant_id", "admission_no", name="uq_student_admission"),)


class Guardian(BaseModel, TenantMixin):
    __tablename__ = "guardians"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    full_name = db.Column(db.String(120), nullable=False)
    relation = db.Column(db.String(40), nullable=False)
    phone = db.Column(db.String(30), nullable=True)

    user = db.relationship("User", backref="guardian_profile", uselist=False)


class StudentGuardian(BaseModel, TenantMixin):
    __tablename__ = "student_guardians"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    guardian_id = db.Column(db.Integer, db.ForeignKey("guardians.id"), nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    student = db.relationship("Student", backref="guardian_links")
    guardian = db.relationship("Guardian", backref="student_links")


class TeacherProfile(BaseModel, TenantMixin):
    __tablename__ = "teacher_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    employee_code = db.Column(db.String(40), nullable=False)
    specialization = db.Column(db.String(120), nullable=True)

    user = db.relationship("User", backref="teacher_profile", uselist=False)


class Enrollment(BaseModel, TenantMixin):
    __tablename__ = "enrollments"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="active")

    student = db.relationship("Student", backref="enrollments")
    classroom = db.relationship("Classroom", backref="enrollments")
    section = db.relationship("Section", backref="enrollments")
    batch = db.relationship("Batch", backref="enrollments")
