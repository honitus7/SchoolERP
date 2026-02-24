from flask import Blueprint

bp = Blueprint("teacher", __name__, template_folder="../../templates", url_prefix="/teacher")

from app.blueprints.teacher import routes  # noqa: E402,F401
