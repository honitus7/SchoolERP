from __future__ import annotations

from datetime import datetime

from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models.identity import User


def login_with_password(username_or_email: str, password: str):
    user = User.query.filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()
    if not user or not user.check_password(password):
        return None

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    return {
        "user": {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "roles": [r.name for r in user.roles],
        },
        "tokens": {
            "access": create_access_token(identity=str(user.id), additional_claims={"roles": [r.name for r in user.roles]}),
            "refresh": create_refresh_token(identity=str(user.id)),
        },
    }
