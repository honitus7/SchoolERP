from __future__ import annotations

from app.extensions import db
from app.models.finance import FeeInstallment, FeeLedger, FeeReceipt, FeeStructure


def create_structure(tenant_id: int, class_id: int, title: str, total_amount: float):
    obj = FeeStructure(tenant_id=tenant_id, class_id=class_id, title=title, total_amount=total_amount)
    db.session.add(obj)
    db.session.commit()
    return obj


def create_installment(tenant_id: int, structure_id: int, title: str, amount: float, due_date):
    obj = FeeInstallment(
        tenant_id=tenant_id,
        structure_id=structure_id,
        title=title,
        amount=amount,
        due_date=due_date,
    )
    db.session.add(obj)
    db.session.commit()
    return obj


def create_receipt(tenant_id: int, ledger_id: int, amount: float, payment_mode: str, reference_no: str | None):
    ledger = db.session.get(FeeLedger, ledger_id)
    if not ledger:
        raise ValueError("Fee ledger not found")
    receipt = FeeReceipt(
        tenant_id=tenant_id,
        ledger_id=ledger_id,
        amount=amount,
        payment_mode=payment_mode,
        reference_no=reference_no,
    )
    ledger.amount_paid += amount
    if ledger.amount_paid >= ledger.amount_due:
        ledger.status = "paid"
    elif ledger.amount_paid > 0:
        ledger.status = "partial"
    db.session.add(receipt)
    db.session.commit()
    return receipt


def ledgers_for_student(tenant_id: int, student_id: int):
    return FeeLedger.query.filter_by(tenant_id=tenant_id, student_id=student_id).all()
