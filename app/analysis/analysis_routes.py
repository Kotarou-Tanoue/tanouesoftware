"""AI分析・不足情報の追加質問・分析結果画面のルーティング。

既存設計書に基づく Flask Blueprint。実際の AI 処理・DB 保存は
DamageAnalysisService 側に委譲し、このモジュールでは実行しない。

想定するサービス登録:
    app.extensions["damage_analysis_service"] = DamageAnalysisService(...)

サービスの契約:
    service.analyze(
        report_id=int | None,
        guest_analysis=dict | None,
        answers=list[dict[str, str]],
        user_id=int | str | None,
    ) -> dict

    戻り値（追加質問）:
        {"status": "needs_followup", "question": "質問文"}
    戻り値（分析完了）:
        {"status": "completed", "result": {
            "damage_level": 1,  # 1〜5
            "repair_cost_min": 10000,  # int または None
            "repair_cost_max": 30000,  # int または None
            "description": "...",
            # 写真の表示情報、被害箇所などは画面仕様に合わせて追加可能
        }}

    service.save_result(
        report_id=int,
        result=dict,
        user_id=int | str,
    ) -> None

事前に入力担当側で session['report_id']（ログイン利用時）または
session['guest_analysis']（未ログイン利用時）をセットする。
ログイン時には session['user_id'] も必要（認証担当とキー名を統一すること）。
サービスは必ず report_id の所有者確認を行うこと。
"""

from __future__ import annotations

import hmac
import json
import secrets
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")

MAX_ANSWER_LENGTH = 2000
MAX_FOLLOWUP_ROUNDS = 5
MAX_RESULT_JSON_BYTES = 128 * 1024


class InvalidAnalysisResult(ValueError):
    """分析サービスからの応答形式が正しくない。"""


def _csrf_token() -> str:
    token = session.get("analysis_csrf_token")
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session["analysis_csrf_token"] = token
    return token


def _validate_csrf() -> None:
    submitted = request.headers.get("X-CSRF-Token", "")
    if not submitted:
        submitted = request.form.get("csrf_token", "")
    expected = session.get("analysis_csrf_token", "")
    if not isinstance(expected, str) or not hmac.compare_digest(submitted, expected):
        abort(400, description="不正なリクエストです。ページを再読み込みしてください。")


def _wants_json() -> bool:
    return request.is_json or (
        request.accept_mimetypes.best == "application/json"
    )


def _report_id() -> int | None:
    raw_id = session.get("report_id")
    if raw_id is None:
        return None
    if isinstance(raw_id, bool):
        return None
    try:
        value = int(raw_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _input_context() -> dict[str, Any] | None:
    report_id = _report_id()
    guest = session.get("guest_analysis")
    if report_id is not None:
        # DB 側データはサービスが取り出す。report_id の所有者確認もサービスの責任。
        return {
            "report_id": report_id,
            "guest_analysis": None,
            "user_id": session.get("user_id"),
        }
    if isinstance(guest, dict) and guest:
        return {"report_id": None, "guest_analysis": guest, "user_id": None}
    return None


def _service() -> Any:
    service = current_app.extensions.get("damage_analysis_service")
    if service is None:
        raise RuntimeError("DamageAnalysisService が未登録です")
    return service


def _validate_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise InvalidAnalysisResult("result は辞書形式である必要があります")

    level = result.get("damage_level")
    if type(level) is not int or not 1 <= level <= 5:
        raise InvalidAnalysisResult("damage_level は1～5の整数です")

    lower = result.get("repair_cost_min")
    upper = result.get("repair_cost_max")
    for name, cost in (("repair_cost_min", lower), ("repair_cost_max", upper)):
        if cost is not None and (type(cost) is not int or cost < 0):
            raise InvalidAnalysisResult(f"{name} は0以上の整数かnullです")
    if lower is not None and upper is not None and lower > upper:
        raise InvalidAnalysisResult("修理費用の下限が上限を超えています")

    # Flask-Session の JSON シリアライザで保存できる構造であることを確認。
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidAnalysisResult("result はJSONで表現できる必要があります") from exc
    if len(encoded.encode("utf-8")) > MAX_RESULT_JSON_BYTES:
        raise InvalidAnalysisResult("結果データのサイズが上限を超えています")
    return result


def _process_analysis() -> str:
    """分析を1回実行し、次に表示する endpoint 名を返す。"""
    context = _input_context()
    if context is None:
        return "analysis.failure"
    if context["report_id"] is not None and context["user_id"] is None:
        current_app.logger.warning("ログイン利用者の user_id がありません")
        return "analysis.failure"

    answers = session.get("analysis_answers", [])
    if not isinstance(answers, list):
        answers = []

    try:
        service = _service()
        response = service.analyze(
            report_id=context["report_id"],
            guest_analysis=context["guest_analysis"],
            answers=answers,
            user_id=context["user_id"],
        )
        if not isinstance(response, dict):
            raise InvalidAnalysisResult("AI分析の応答が辞書ではありません")

        status = response.get("status")
        if status == "needs_followup":
            question = response.get("question")
            if not isinstance(question, str) or not question.strip():
                raise InvalidAnalysisResult("追加質問が空です")
            if len(answers) >= MAX_FOLLOWUP_ROUNDS:
                session["analysis_error"] = "追加質問の回数が上限に達しました。"
                return "analysis.failure"
            session["analysis_followup"] = {"question": question.strip()[:1000]}
            session.pop("analysis_error", None)
            return "analysis.followup"

        if status == "completed":
            result = _validate_result(response.get("result"))
            if context["report_id"] is not None:
                # 失敗時に「保存済み」と見せない。DB操作はサービス側で実装する。
                service.save_result(
                    report_id=context["report_id"],
                    result=result,
                    user_id=context["user_id"],
                )
            session["analysis_result"] = result
            session.pop("analysis_followup", None)
            session.pop("analysis_answers", None)
            session.pop("analysis_error", None)
            return "analysis.result"

        raise InvalidAnalysisResult("未知の分析ステータスです")
    except TimeoutError:
        current_app.logger.warning("AI分析がタイムアウトしました")
        session["analysis_error"] = "分析がタイムアウトしました。もう一度お試しください。"
    except Exception:
        # 詳細な例外やAPIキー等をHTML/JSONに直接返さない。
        current_app.logger.exception("AI分析の実行または保存に失敗しました")
        session["analysis_error"] = "AI分析に失敗しました。もう一度お試しください。"
    return "analysis.failure"


def _respond_with_destination(endpoint: str):
    destination = url_for(endpoint)
    if _wants_json():
        return jsonify(
            {"status": endpoint.rsplit(".", 1)[-1], "redirect_url": destination}
        )
    return redirect(destination, code=303)


@analysis_bp.get("")
def index():
    """GET /analysis : 分析中画面を表示する。"""
    if _input_context() is None:
        return redirect(url_for("index"))

    # 被害状況入力画面から新たに遷移したときは分析状態を初期化する。
    for key in ("analysis_answers", "analysis_followup", "analysis_result", "analysis_error"):
        session.pop(key, None)

    return render_template(
        "analysis/analyzing.html",
        csrf_token=_csrf_token(),
        run_url=url_for("analysis.run"),
    )


@analysis_bp.post("/run")
def run():
    """POST /analysis/run : AI分析開始。fetch() またはフォーム送信で呼び出す。"""
    _validate_csrf()
    if _input_context() is None:
        abort(400, description="分析対象の情報がありません。")
    if session.get("analysis_followup"):
        abort(409, description="追加質問への回答が必要です。")
    return _respond_with_destination(_process_analysis())


@analysis_bp.route("/followup", methods=["GET", "POST"])
def followup():
    """追加質問画面の表示と回答受付。"""
    pending = session.get("analysis_followup")
    if not isinstance(pending, dict) or not pending.get("question"):
        return redirect(url_for("analysis.index"))

    if request.method == "GET":
        return render_template(
            "analysis/analysis_additional_chat.html",
            question=pending["question"],
            answers=session.get("analysis_answers", []),
            csrf_token=_csrf_token(),
            answer_url=url_for("analysis.followup"),
            error=None,
        )

    _validate_csrf()
    data = request.get_json(silent=True) if request.is_json else request.form
    answer = data.get("answer", "") if isinstance(data, dict) or hasattr(data, "get") else ""
    if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER_LENGTH:
        if _wants_json():
            return jsonify({"error": "回答を1～2000文字以内で入力してください。"}), 400
        return render_template(
            "analysis/analysis_additional_chat.html",
            question=pending["question"],
            answers=session.get("analysis_answers", []),
            csrf_token=_csrf_token(),
            answer_url=url_for("analysis.followup"),
            error="回答を1～2000文字以内で入力してください。",
        ), 400

    answers = session.get("analysis_answers", [])
    if not isinstance(answers, list):
        answers = []
    if len(answers) >= MAX_FOLLOWUP_ROUNDS:
        session["analysis_error"] = "追加質問の回数が上限に達しました。"
        return _respond_with_destination("analysis.failure")
    answers.append({"question": str(pending["question"]), "answer": answer.strip()})
    session["analysis_answers"] = answers
    session.pop("analysis_followup", None)
    return _respond_with_destination(_process_analysis())


@analysis_bp.get("/result")
def result():
    """GET /analysis/result : 完了した分析結果を表示する。"""
    data = session.get("analysis_result")
    if not isinstance(data, dict):
        return redirect(url_for("analysis.index"))
    return render_template("analysis/analysis_result.html", result=data)


@analysis_bp.get("/failure")
def failure():
    """GET /analysis/failure : 分析失敗画面を表示する。"""
    message = session.get("analysis_error", "分析を完了できませんでした。")
    return render_template("analysis/analysis_failure.html", error_message=message)
