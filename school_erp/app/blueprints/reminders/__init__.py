from flask import Blueprint

bp = Blueprint("reminders", __name__, template_folder="../../templates", url_prefix="/reminders")

from app.blueprints.reminders import routes  # noqa: E402,F401
