from flask import Blueprint

bp = Blueprint("transport", __name__, template_folder="../../templates", url_prefix="/transport")

from app.blueprints.transport import routes  # noqa: E402,F401
