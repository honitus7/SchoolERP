from flask import Blueprint

bp = Blueprint("notices", __name__, template_folder="../../templates", url_prefix="/notices")

from app.blueprints.notices import routes  # noqa: E402,F401
