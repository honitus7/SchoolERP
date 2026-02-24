from flask import Blueprint

bp = Blueprint("parent", __name__, template_folder="../../templates", url_prefix="/parent")

from app.blueprints.parent import routes  # noqa: E402,F401
