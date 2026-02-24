from flask import Blueprint

bp = Blueprint("calendar", __name__, template_folder="../../templates", url_prefix="/calendar")

from app.blueprints.calendar import routes  # noqa: E402,F401
