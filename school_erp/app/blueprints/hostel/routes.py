from __future__ import annotations

from flask import render_template

from app.blueprints.hostel import bp
from app.core.auth import current_user, login_required
from app.core.rbac import role_required


@bp.get("/")
@login_required
@role_required("admin")
def hostel_page():
    user = current_user()
    return render_template(
        "pages/modules/module_page.html",
        module_key="hostel",
        module_title="Hostel",
        user=user,
    )
