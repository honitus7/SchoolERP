from __future__ import annotations

from app.extensions import db
from app.models.base import BaseModel, TenantMixin


class AdmissionForm(BaseModel, TenantMixin):
    __tablename__ = "admission_forms"

    student_name = db.Column(db.String(120), nullable=False)
    guardian_name = db.Column(db.String(120), nullable=False)
    target_class = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="submitted")


class AdmissionStatusHistory(BaseModel, TenantMixin):
    __tablename__ = "admission_status_history"

    admission_form_id = db.Column(db.Integer, db.ForeignKey("admission_forms.id"), nullable=False)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class TransportRoute(BaseModel, TenantMixin):
    __tablename__ = "transport_routes"

    name = db.Column(db.String(120), nullable=False)
    shift = db.Column(db.String(20), nullable=False, default="morning")


class Vehicle(BaseModel, TenantMixin):
    __tablename__ = "vehicles"

    registration_no = db.Column(db.String(40), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=30)


class RouteStop(BaseModel, TenantMixin):
    __tablename__ = "route_stops"

    route_id = db.Column(db.Integer, db.ForeignKey("transport_routes.id"), nullable=False)
    stop_name = db.Column(db.String(120), nullable=False)
    stop_order = db.Column(db.Integer, nullable=False)


class StudentTransportAssignment(BaseModel, TenantMixin):
    __tablename__ = "student_transport_assignments"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey("transport_routes.id"), nullable=False)
    stop_id = db.Column(db.Integer, db.ForeignKey("route_stops.id"), nullable=True)


class PayrollCycle(BaseModel, TenantMixin):
    __tablename__ = "payroll_cycles"

    month_label = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")


class SalaryComponent(BaseModel, TenantMixin):
    __tablename__ = "salary_components"

    teacher_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    component_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)


class PayrollEntry(BaseModel, TenantMixin):
    __tablename__ = "payroll_entries"

    cycle_id = db.Column(db.Integer, db.ForeignKey("payroll_cycles.id"), nullable=False)
    teacher_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    gross_pay = db.Column(db.Float, nullable=False)
    net_pay = db.Column(db.Float, nullable=False)


class Book(BaseModel, TenantMixin):
    __tablename__ = "books"

    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(120), nullable=False)
    isbn = db.Column(db.String(40), nullable=True)


class BookCopy(BaseModel, TenantMixin):
    __tablename__ = "book_copies"

    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    copy_code = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="available")


class BookLoan(BaseModel, TenantMixin):
    __tablename__ = "book_loans"

    copy_id = db.Column(db.Integer, db.ForeignKey("book_copies.id"), nullable=False)
    borrower_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.DateTime, nullable=True)


class Hostel(BaseModel, TenantMixin):
    __tablename__ = "hostels"

    name = db.Column(db.String(120), nullable=False)


class Room(BaseModel, TenantMixin):
    __tablename__ = "rooms"

    hostel_id = db.Column(db.Integer, db.ForeignKey("hostels.id"), nullable=False)
    room_no = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=4)


class HostelAllocation(BaseModel, TenantMixin):
    __tablename__ = "hostel_allocations"

    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)


class InventoryItem(BaseModel, TenantMixin):
    __tablename__ = "inventory_items"

    name = db.Column(db.String(120), nullable=False)
    sku = db.Column(db.String(40), nullable=True)
    quantity = db.Column(db.Float, nullable=False, default=0)


class StockMove(BaseModel, TenantMixin):
    __tablename__ = "stock_moves"

    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    move_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(255), nullable=True)


class Vendor(BaseModel, TenantMixin):
    __tablename__ = "vendors"

    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=True)


class PurchaseRecord(BaseModel, TenantMixin):
    __tablename__ = "purchase_records"

    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
