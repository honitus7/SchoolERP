from __future__ import annotations

from flask import render_template

from app.blueprints.hostel import bp
from app.core.auth import current_user, login_required


@bp.get("/")
@login_required
def hostel_page():
    user = current_user()
    return render_template(
        "pages/modules/module_page.html",
        module_key="hostel",
        module_title="Hostel",
        user=user,
    )
