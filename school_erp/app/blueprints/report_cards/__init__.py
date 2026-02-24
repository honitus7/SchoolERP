from flask import Blueprint

bp = Blueprint("report_cards", __name__, template_folder="../../templates", url_prefix="/report-cards")

from app.blueprints.report_cards import routes  # noqa: E402,F401
