from __future__ import annotations

from datetime import date, datetime, timedelta

from app.extensions import db
from app.models.academic import Classroom, Enrollment, Guardian, Section, Student, StudentGuardian, Subject, TeacherProfile
from app.models.communication import CalendarEntry, Event, Notice, Reminder
from app.models.enterprise import Hostel, InventoryItem, PayrollCycle, TransportRoute
from app.models.finance import FeeInstallment, FeeLedger, FeeStructure
from app.models.identity import Role, Tenant, User


def _get_or_create(model, defaults=None, **kwargs):
    defaults = defaults or {}
    obj = model.query.filter_by(**kwargs).first()
    if obj:
        return obj
    params = dict(kwargs)
    params.update(defaults)
    obj = model(**params)
    db.session.add(obj)
    db.session.flush()
    return obj


def seed_data() -> None:
    tenant = _get_or_create(Tenant, name="Demo School", code="demo-school")

    roles = {}
    for role_name in ["admin", "teacher", "parent", "student"]:
        roles[role_name] = _get_or_create(Role, name=role_name, description=f"{role_name} role")

    users_cfg = [
        ("admin", "admin@demo.local", "System Admin", "admin123", ["admin"]),
        ("teacher", "teacher@demo.local", "Riya Teacher", "teacher123", ["teacher"]),
        ("parent", "parent@demo.local", "Arjun Parent", "parent123", ["parent"]),
        ("student", "student@demo.local", "Anvi Student", "student123", ["student"]),
    ]

    users = {}
    for username, email, full_name, password, user_roles in users_cfg:
        user = User.query.filter_by(tenant_id=tenant.id, username=username).first()
        if not user:
            user = User(
                tenant_id=tenant.id,
                username=username,
                email=email,
                full_name=full_name,
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        for role_name in user_roles:
            role = roles[role_name]
            if role not in user.roles:
                user.roles.append(role)
        users[username] = user

    cls = _get_or_create(Classroom, tenant_id=tenant.id, name="Class 10", academic_year="2025-26")
    section = _get_or_create(Section, tenant_id=tenant.id, class_id=cls.id, name="A")
    math = _get_or_create(Subject, tenant_id=tenant.id, code="MAT", name="Mathematics")
    _get_or_create(Subject, tenant_id=tenant.id, code="SCI", name="Science")

    student = _get_or_create(
        Student,
        tenant_id=tenant.id,
        admission_no="ADM1001",
        defaults={
            "user_id": users["student"].id,
            "full_name": "Anvi Student",
            "class_id": cls.id,
            "section_id": section.id,
        },
    )

    guardian = _get_or_create(
        Guardian,
        tenant_id=tenant.id,
        defaults={
            "user_id": users["parent"].id,
            "full_name": "Arjun Parent",
            "relation": "father",
            "phone": "+91-9999999999",
        },
        full_name="Arjun Parent",
        relation="father",
    )

    _get_or_create(StudentGuardian, tenant_id=tenant.id, student_id=student.id, guardian_id=guardian.id, defaults={"is_primary": True})

    _get_or_create(
        TeacherProfile,
        tenant_id=tenant.id,
        user_id=users["teacher"].id,
        employee_code="EMP-T-100",
        defaults={"specialization": "Math"},
    )

    _get_or_create(Enrollment, tenant_id=tenant.id, student_id=student.id, class_id=cls.id, section_id=section.id, defaults={"status": "active"})

    fee_structure = _get_or_create(
        FeeStructure,
        tenant_id=tenant.id,
        class_id=cls.id,
        title="Annual Fee 2025-26",
        defaults={"total_amount": 50000},
    )

    installment = _get_or_create(
        FeeInstallment,
        tenant_id=tenant.id,
        structure_id=fee_structure.id,
        title="Quarter 1",
        defaults={"amount": 12500, "due_date": date.today() + timedelta(days=7)},
    )

    _get_or_create(
        FeeLedger,
        tenant_id=tenant.id,
        student_id=student.id,
        installment_id=installment.id,
        defaults={"amount_due": 12500, "amount_paid": 0, "status": "overdue"},
    )

    _get_or_create(
        Notice,
        tenant_id=tenant.id,
        title="Welcome Session",
        defaults={
            "body": "Orientation starts at 9:00 AM tomorrow.",
            "posted_by": users["admin"].id,
            "audience": "all",
        },
    )

    event = _get_or_create(
        Event,
        tenant_id=tenant.id,
        title="Math Weekly Test",
        defaults={
            "details": "Chapter 1 to 3",
            "starts_at": datetime.utcnow() + timedelta(days=2),
            "ends_at": datetime.utcnow() + timedelta(days=2, hours=2),
            "event_type": "exam",
        },
    )

    _get_or_create(
        Reminder,
        tenant_id=tenant.id,
        title="Fee Reminder",
        defaults={
            "content": "Pay Quarter 1 fee before due date.",
            "remind_at": datetime.utcnow() + timedelta(days=3),
            "created_by": users["admin"].id,
        },
    )

    _get_or_create(
        CalendarEntry,
        tenant_id=tenant.id,
        title=event.title,
        starts_at=event.starts_at,
        defaults={
            "ends_at": event.ends_at,
            "entry_type": "event",
            "reference_type": "event",
            "reference_id": event.id,
        },
    )

    _get_or_create(TransportRoute, tenant_id=tenant.id, name="Route A", defaults={"shift": "morning"})
    _get_or_create(PayrollCycle, tenant_id=tenant.id, month_label="2026-02", defaults={"status": "draft"})
    _get_or_create(Hostel, tenant_id=tenant.id, name="Boys Hostel")
    _get_or_create(InventoryItem, tenant_id=tenant.id, name="Projector", defaults={"sku": "INV-PROJ-1", "quantity": 3})

    db.session.commit()
