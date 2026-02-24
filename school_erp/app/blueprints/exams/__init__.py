from flask import Blueprint

bp = Blueprint("exams", __name__, template_folder="../../templates", url_prefix="/exams")

from app.blueprints.exams import routes  # noqa: E402,F401
