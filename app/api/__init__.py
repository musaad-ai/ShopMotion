from flask import Blueprint

api_bp = Blueprint("api", __name__)

from . import analytics, live, system  # noqa: E402,F401
