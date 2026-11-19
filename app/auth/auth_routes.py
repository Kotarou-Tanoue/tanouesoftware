from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.models.user import User

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)


# ログインページ
@auth_bp.route("/login")
def login():
    return render_template("auth/login.html")


# 開発用ログインページ
@auth_bp.route("/login/dev", methods=["GET", "POST"])
def dev_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)

        if user_id not in (2, 3):
            return "不正なユーザーIDです", 400

        user = User.query.get(user_id)

        if user is None:
            return "ユーザーが存在しません", 404

        login_user(user)

        return redirect(url_for("auth.dev_login"))
    return render_template("auth/dev_login.html")


# ログアウトページ
@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "POST":
        logout_user()
        return redirect(url_for("index"))

    if not current_user.is_authenticated:
        return render_template("auth/login.html")

    return render_template("auth/logout.html")
