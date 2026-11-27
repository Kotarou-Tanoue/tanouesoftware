from flask import render_template, request, url_for
from flask_login import current_user

from . import recovery_bp


@recovery_bp.get("/")
def index():
    """復旧情報画面を表示する。"""

    # 遷移元と分析IDを取得
    source = request.args.get("source")
    analysis_id = request.args.get("analysis_id", type=int)

    back_url = None
    back_label = None

    # 分析結果から遷移した場合
    if source == "result":
        back_url = url_for("analysis.result")
        back_label = "分析結果に戻る"

    # 分析履歴詳細から遷移した場合
    elif (
        source == "history"
        and current_user.is_authenticated
        and analysis_id is not None
    ):
        back_url = url_for(
            "history.show_history_detail",
            analysis_id=analysis_id,
        )
        back_label = "分析履歴に戻る"

    # ログイン時にメニューから遷移した場合
    elif source == "menu" and current_user.is_authenticated:
        back_url = url_for("history.show_history")
        back_label = "履歴を見る"

    return render_template(
        "recovery/index.html",
        back_url=back_url,
        back_label=back_label,
    )
