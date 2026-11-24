from datetime import datetime

from flask import render_template
from flask_login import login_required, current_user

from app.mypage import mypage_bp
from app.models import Building, DamageReport, AnalysisHistory
from app.common.photos import get_first_photo_keys


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

    # 分析履歴のreport_idを取得
    report_ids = [history.report_id for history in histories]

    # 各分析履歴の1枚目の写真を取得
    photo_keys = get_first_photo_keys(
        report_ids,
        current_user.user_id
    )

    print("report_ids:", report_ids)
    print("photo_keys:", photo_keys)

    # マイページを表示
    return render_template(
        "mypage/mypage.html",
        buildings=buildings,
        histories=histories,
        now_year=datetime.now().year,
        photo_keys=photo_keys
    )