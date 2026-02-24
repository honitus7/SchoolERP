from __future__ import annotations

from flask import render_template

from app.blueprints.reminders import bp
from app.core.auth import current_user, login_required
from app.core.rbac import role_required


@bp.get("/")
@login_required
@role_required("admin", "teacher", "parent", "student")
def reminders_page():
    user = current_user()
    return render_template(
        "pages/modules/module_page.html",
        module_key="reminders",
        module_title="Reminders",
        user=user,
    )
