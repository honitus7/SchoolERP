from __future__ import annotations

from flask import Flask

from app.extensions import csrf


def register_blueprints(app: Flask) -> None:
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.admissions import bp as admissions_bp
    from app.blueprints.api_v1 import bp as api_v1_bp
    from app.blueprints.attendance import bp as attendance_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.calendar import bp as calendar_bp
    from app.blueprints.coaching import bp as coaching_bp
    from app.blueprints.dashboard import bp as dashboard_bp
    from app.blueprints.events import bp as events_bp
    from app.blueprints.exams import bp as exams_bp
    from app.blueprints.fees import bp as fees_bp
    from app.blueprints.hostel import bp as hostel_bp
    from app.blueprints.inventory import bp as inventory_bp
    from app.blueprints.library import bp as library_bp
    from app.blueprints.messaging import bp as messaging_bp
    from app.blueprints.notices import bp as notices_bp
    from app.blueprints.parent import bp as parent_bp
    from app.blueprints.payroll import bp as payroll_bp
    from app.blueprints.reminders import bp as reminders_bp
    from app.blueprints.report_cards import bp as report_cards_bp
    from app.blueprints.student import bp as student_bp
    from app.blueprints.teacher import bp as teacher_bp
    from app.blueprints.transport import bp as transport_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(student_bp)

    app.register_blueprint(attendance_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(report_cards_bp)
    app.register_blueprint(fees_bp)
    app.register_blueprint(notices_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(messaging_bp)
    app.register_blueprint(calendar_bp)

    app.register_blueprint(admissions_bp)
    app.register_blueprint(transport_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(hostel_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(coaching_bp)

    csrf.exempt(api_v1_bp)
    app.register_blueprint(api_v1_bp)
