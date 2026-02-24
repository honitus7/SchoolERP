from flask import Blueprint

bp = Blueprint("coaching", __name__, template_folder="../../templates", url_prefix="/coaching")

from app.blueprints.coaching import routes  # noqa: E402,F401
