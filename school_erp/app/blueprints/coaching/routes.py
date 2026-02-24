from __future__ import annotations

from flask import render_template

from app.blueprints.coaching import bp
from app.core.auth import current_user, login_required


@bp.get("/")
@login_required
def coaching_page():
    user = current_user()
    return render_template(
        "pages/modules/module_page.html",
        module_key="coaching",
        module_title="Coaching",
        user=user,
    )
