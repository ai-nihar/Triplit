from __future__ import annotations

from flask import Blueprint

from controllers.home_controller import index

web_bp = Blueprint("web", __name__)

web_bp.get("/")(index)
