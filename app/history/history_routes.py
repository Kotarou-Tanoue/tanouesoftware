from flask import render_template
from flask_login import login_required, current_user

from app.history import history_bp
from app.models import Building, DamageReport, AnalysisHistory
from app.common.photos import get_first_photo_keys, get_photo_keys_for_report


@history_bp.route("/", methods=["GET"])
@login_required
def show_history():

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

    # 分析履歴に対応するreport_idを取得
    report_ids = [
        history.report_id for history in histories
    ]

    # 各分析履歴の1枚目の写真を取得
    photo_keys = get_first_photo_keys(
        report_ids,
        current_user.user_id
    )

    # 分析履歴一覧画面を表示
    return render_template(
        "history/history_list.html",
        histories=histories,
        photo_keys=photo_keys
    )

@history_bp.route("/<int:analysis_id>", methods=["GET"])
@login_required
def show_history_detail(analysis_id):

    # ログイン中の利用者が所有する分析履歴を取得
    history = AnalysisHistory.query.join(
        DamageReport,
        AnalysisHistory.report_id == DamageReport.report_id
    ).join(
        Building,
        DamageReport.building_id == Building.building_id
    ).filter(
        AnalysisHistory.analysis_id == analysis_id,
        Building.user_id == current_user.user_id
    ).first_or_404()

    # 分析に使用した写真を取得
    photo_keys = get_photo_keys_for_report(
        history.report_id,
        current_user.user_id
    )

    # チャット履歴を取得
    chat_histories = history.chat_histories

    # 分析履歴詳細画面を表示
    return render_template(
        "history/history_detail.html",
        history=history,
        chat_histories=chat_histories,
        photo_keys=photo_keys
    )