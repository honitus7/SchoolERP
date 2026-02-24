from flask import Blueprint

bp = Blueprint("library", __name__, template_folder="../../templates", url_prefix="/library")

from app.blueprints.library import routes  # noqa: E402,F401
