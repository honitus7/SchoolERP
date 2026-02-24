from flask import Blueprint

bp = Blueprint("admissions", __name__, template_folder="../../templates", url_prefix="/admissions")

from app.blueprints.admissions import routes  # noqa: E402,F401
