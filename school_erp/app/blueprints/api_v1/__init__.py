from flask import Blueprint

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

from app.blueprints.api_v1 import routes  # noqa: E402,F401
