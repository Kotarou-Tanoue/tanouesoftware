from flask import Blueprint

mypage_bp = Blueprint(
    "mypage",
    __name__,
)

from . import mypage_routes