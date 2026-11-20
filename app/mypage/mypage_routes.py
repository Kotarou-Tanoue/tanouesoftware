from flask import render_template
from flask_login import login_required, current_user

from app.mypage import mypage_bp
from app.models import Building, DamageReport, AnalysisHistory


@mypage_bp.route("/", methods=["GET"])
@login_required
def show_mypage():

    # ログイン中の利用者が登録した建物を取得
    buildings = Building.query.filter_by(
        user_id=current_user.user_id
    ).order_by(
        Building.building_id.desc()
    ).all()

    # ログイン中の利用者が所有する建物の分析履歴を取得
    histories = AnalysisHistory.query.join(
        DamageReport,
        AnalysisHistory.report_id == DamageReport.report_id
    ).join(
        Building,
        DamageReport.building_id == Building.building_id
    ).filter(
        Building.user_id == current_user.user_id
    ).order_by(
        AnalysisHistory.created_at.desc()
    ).all()

    # マイページを表示
    return render_template(
        "mypage/mypage.html",
        buildings=buildings,
        histories=histories
    )