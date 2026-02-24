from flask import Blueprint

bp = Blueprint("payroll", __name__, template_folder="../../templates", url_prefix="/payroll")

from app.blueprints.payroll import routes  # noqa: E402,F401
