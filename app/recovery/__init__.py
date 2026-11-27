from flask import Blueprint, render_template

recovery_bp = Blueprint("recovery", __name__, url_prefix="/recovery")

from . import routes
