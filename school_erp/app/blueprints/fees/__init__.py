from flask import Blueprint

bp = Blueprint("fees", __name__, template_folder="../../templates", url_prefix="/fees")

from app.blueprints.fees import routes  # noqa: E402,F401
