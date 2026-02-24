from __future__ import annotations

from flask import render_template

from app.blueprints.notices import bp
from app.core.auth import current_user, login_required


@bp.get("/")
@login_required
def notices_page():
    user = current_user()
    return render_template(
        "pages/modules/module_page.html",
        module_key="notices",
        module_title="Notice Board",
        user=user,
    )
