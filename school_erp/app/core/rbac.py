from __future__ import annotations

from functools import wraps

from flask import abort, request

from app.core.auth import current_user
from app.core.responses import fail


def role_required(*roles: str):
    role_set = {r.lower() for r in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return fail("Authentication required", status=401, code="unauthorized")
            if not any(role.name.lower() in role_set for role in user.roles):
                if request.path.startswith("/api/"):
                    return fail("Forbidden", status=403, code="forbidden")
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
