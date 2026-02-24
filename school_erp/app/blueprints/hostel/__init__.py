from flask import Blueprint

bp = Blueprint("hostel", __name__, template_folder="../../templates", url_prefix="/hostel")

from app.blueprints.hostel import routes  # noqa: E402,F401
