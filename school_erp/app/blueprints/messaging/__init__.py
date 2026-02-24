from flask import Blueprint

bp = Blueprint("messaging", __name__, template_folder="../../templates", url_prefix="/messaging")

from app.blueprints.messaging import routes  # noqa: E402,F401
