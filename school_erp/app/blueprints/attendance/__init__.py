from flask import Blueprint

bp = Blueprint("attendance", __name__, template_folder="../../templates", url_prefix="/attendance")

from app.blueprints.attendance import routes  # noqa: E402,F401
