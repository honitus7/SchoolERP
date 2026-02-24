from __future__ import annotations

from flask import redirect, render_template, request, session, url_for
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required

from app.blueprints.auth import bp
from app.core.auth import current_user, login_user, logout_user
from app.core.responses import fail, ok
from app.core.validators import require_fields
from app.extensions import csrf, db
from app.models.identity import User
from app.services.auth_service import login_with_password


@bp.route("/", methods=["GET"])
def home_redirect():
    user = current_user()
    if user:
        role = user.roles[0].name.lower() if user.roles else "admin"
        return redirect(url_for("dashboard.role_dashboard", role=role))
    return redirect(url_for("auth.login_page"))


@bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("pages/auth/login.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    result = login_with_password(username, password)
    if not result:
        return render_template("pages/auth/login.html", error="Invalid credentials"), 401

    user = db.session.get(User, int(result["user"]["id"]))
    login_user(user)
    role = user.roles[0].name.lower() if user.roles else "admin"
    return redirect(url_for("dashboard.role_dashboard", role=role))


@bp.route("/logout", methods=["POST", "GET"])
def logout_page():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login_page"))


@bp.post("/api/v1/auth/login")
@csrf.exempt
def api_login():
    payload = request.get_json(silent=True) or {}
    valid, missing = require_fields(payload, ["username", "password"])
    if not valid:
        return fail("Missing required fields", details={"missing": missing})

    result = login_with_password(payload["username"], payload["password"])
    if not result:
        return fail("Invalid credentials", status=401, code="unauthorized")

    return ok(result)


@bp.post("/api/v1/auth/logout")
@jwt_required(optional=True)
@csrf.exempt
def api_logout():
    return ok({"status": "logged_out"})


@bp.post("/api/v1/auth/refresh")
@jwt_required(refresh=True)
@csrf.exempt
def api_refresh():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity)) if identity else None
    roles = [r.name for r in user.roles] if user else []
    access = create_access_token(identity=identity, additional_claims={"roles": roles})
    return ok({"access": access})


@bp.post("/api/v1/auth/password/reset-request")
@csrf.exempt
def api_reset_request():
    payload = request.get_json(silent=True) or {}
    if not payload.get("email"):
        return fail("Email is required")
    return ok({"status": "queued", "message": "Reset workflow stubbed for v1"})


@bp.post("/api/v1/auth/password/reset")
@csrf.exempt
def api_reset():
    payload = request.get_json(silent=True) or {}
    if not payload.get("token") or not payload.get("new_password"):
        return fail("token and new_password are required")
    return ok({"status": "updated", "message": "Reset completion stubbed for v1"})
