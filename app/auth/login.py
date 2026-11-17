from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_user

from app.models.user import User

login_bp = Blueprint(
    "login",
    __name__,
    url_prefix="/login",
)


# ログインページ
@login_bp.route("/")
def LINE_login():
    return render_template("auth/login.html")


# 開発用ログインページ
@login_bp.route("/dev", methods=["GET", "POST"])
def dev_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)

        if user_id not in (2, 3):
            return "不正なユーザーIDです", 400

        user = User.query.get(user_id)

        if user is None:
            return "ユーザーが存在しません", 404

        login_user(user)

        return redirect(url_for("login_bp.dev_login"))
    return render_template("auth/dev_login.html")
