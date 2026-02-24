from __future__ import annotations

from flask import abort, render_template

from app.blueprints.dashboard import bp
from app.core.auth import current_user, login_required
from app.services.dashboard_service import dashboard_summary


@bp.get("/<role>")
@login_required
def role_dashboard(role: str):
    user = current_user()
    user_roles = {r.name.lower() for r in user.roles}
    role = role.lower()
    if role not in user_roles and "admin" not in user_roles:
        abort(403)
    data = dashboard_summary(user.tenant_id, role)
    return render_template("pages/dashboard/role_dashboard.html", dashboard=data, role=role, user=user)
