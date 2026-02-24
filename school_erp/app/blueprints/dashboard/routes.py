from __future__ import annotations

from flask import render_template

from app.blueprints.dashboard import bp
from app.core.auth import current_user, login_required
from app.services.dashboard_service import dashboard_summary


@bp.get("/<role>")
@login_required
def role_dashboard(role: str):
    user = current_user()
    data = dashboard_summary(user.tenant_id, role)
    return render_template("pages/dashboard/role_dashboard.html", dashboard=data, role=role, user=user)
