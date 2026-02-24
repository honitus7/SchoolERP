from __future__ import annotations

from app.extensions import db
from app.models.coaching import CoachingBatch, Course, TestAttempt, TestSeries
from app.models.enterprise import (
    AdmissionForm,
    AdmissionStatusHistory,
    Book,
    BookCopy,
    BookLoan,
    Hostel,
    HostelAllocation,
    InventoryItem,
    PayrollCycle,
    PayrollEntry,
    PurchaseRecord,
    Room,
    RouteStop,
    SalaryComponent,
    StockMove,
    StudentTransportAssignment,
    TransportRoute,
    Vehicle,
    Vendor,
)


MODULE_MODELS = {
    "admissions": AdmissionForm,
    "transport_routes": TransportRoute,
    "vehicles": Vehicle,
    "route_stops": RouteStop,
    "transport_assignments": StudentTransportAssignment,
    "payroll_cycles": PayrollCycle,
    "salary_components": SalaryComponent,
    "payroll_entries": PayrollEntry,
    "books": Book,
    "book_copies": BookCopy,
    "book_loans": BookLoan,
    "hostels": Hostel,
    "rooms": Room,
    "hostel_allocations": HostelAllocation,
    "inventory_items": InventoryItem,
    "stock_moves": StockMove,
    "vendors": Vendor,
    "purchase_records": PurchaseRecord,
    "courses": Course,
    "coaching_batches": CoachingBatch,
    "test_series": TestSeries,
    "test_attempts": TestAttempt,
}


def create_record(module_key: str, tenant_id: int, payload: dict):
    model = MODULE_MODELS[module_key]
    payload["tenant_id"] = tenant_id
    obj = model(**payload)
    db.session.add(obj)
    db.session.commit()
    return obj


def list_records(module_key: str, tenant_id: int):
    model = MODULE_MODELS[module_key]
    return model.query.filter_by(tenant_id=tenant_id).all()


def admission_status_update(tenant_id: int, form_id: int, old_status: str | None, new_status: str, changed_by: int):
    history = AdmissionStatusHistory(
        tenant_id=tenant_id,
        admission_form_id=form_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    )
    db.session.add(history)
    db.session.commit()
    return history
