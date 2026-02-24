from flask import Blueprint

bp = Blueprint("events", __name__, template_folder="../../templates", url_prefix="/events")

from app.blueprints.events import routes  # noqa: E402,F401
