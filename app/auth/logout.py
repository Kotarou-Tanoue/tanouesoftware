from flask import Blueprint, render_template

logout_bp = Blueprint(
    "logout",
    __name__,
    url_prefix="/logout",
)


# ログインページ
@logout_bp.route("/")
def LINE_login():
    return render_template("auth/logout.html")
