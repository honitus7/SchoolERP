from __future__ import annotations

from flask import render_template

from app.blueprints.admin import bp
from app.core.auth import current_user, login_required
from app.core.rbac import role_required


@bp.get("/")
@login_required
@role_required("admin")
def admin_home():
    user = current_user()
    return render_template("pages/dashboard/role_home.html", role="admin", user=user)
