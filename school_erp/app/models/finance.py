from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class FeeStructure(BaseModel, TenantMixin):
    __tablename__ = "fee_structures"

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)


class FeeInstallment(BaseModel, TenantMixin):
    __tablename__ = "fee_installments"

    structure_id = db.Column(db.Integer, db.ForeignKey("fee_structures.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)

    structure = db.relationship("FeeStructure", backref="installments")


class FeeLedger(BaseModel, TenantMixin):
    __tablename__ = "fee_ledgers"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    installment_id = db.Column(db.Integer, db.ForeignKey("fee_installments.id"), nullable=False)
    amount_due = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="overdue")

    student = db.relationship("Student", backref="fee_ledgers")
    installment = db.relationship("FeeInstallment", backref="ledger_entries")


class FeeReceipt(BaseModel, TenantMixin):
    __tablename__ = "fee_receipts"

    ledger_id = db.Column(db.Integer, db.ForeignKey("fee_ledgers.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(30), nullable=False, default="cash")
    reference_no = db.Column(db.String(80), nullable=True)

    ledger = db.relationship("FeeLedger", backref="receipts")


class Concession(BaseModel, TenantMixin):
    __tablename__ = "concessions"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=True)

    student = db.relationship("Student", backref="concessions")
