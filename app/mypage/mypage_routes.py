from flask import render_template

from app.mypage import mypage_bp


@mypage_bp.route("/", methods=["GET"])
def show_mypage():
    return render_template("mypage/mypage.html")