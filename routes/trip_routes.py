from flask import Blueprint

from controllers.trip_controller import index


trip_bp = Blueprint("trip", __name__)


@trip_bp.get("/")
def home():
    return index()
