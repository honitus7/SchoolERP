from __future__ import annotations

from functools import wraps

from flask import redirect, request, session, url_for
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.identity import User


SESSION_USER_KEY = "erp_user_id"


def login_user(user: User) -> None:
    session[SESSION_USER_KEY] = user.id


def logout_user() -> None:
    session.pop(SESSION_USER_KEY, None)


def current_user() -> User | None:
    user_id = session.get(SESSION_USER_KEY)
    if user_id:
        return db.session.get(User, user_id)

    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None

    if identity:
        try:
            identity = int(identity)
        except (TypeError, ValueError):
            pass
        return db.session.get(User, identity)

    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                from app.core.responses import fail

                return fail("Authentication required", status=401, code="unauthorized")
            return redirect(url_for("auth.login_page", next=request.path))
        return view(*args, **kwargs)

    return wrapped
