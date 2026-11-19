"""AI分析・不足情報の追加質問・分析結果画面のルーティング。

既存設計書に基づく Flask Blueprint。実際の AI 処理・DB 保存は
DamageAnalysisService 側に委譲し、このモジュールでは実行しない。

想定するサービス登録:
    app.extensions["damage_analysis_service"] = DamageAnalysisService(...)

サービスの契約:
    service.analyze_damage(
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
            # 設計書のDamageLocationと同名のキーを利用する。
            "damage_locations": [{"location_id": 1, "location_name": "和室", "description": "...", "severity": 2}],
            # 明細は画面用（analysis_historyには保存先がない）。
            "repair_items": [{"name": "天井補修", "cost_min": 10000, "cost_max": 20000}],
            # S3キーと署名付きURLは別物。URLはPhotoStorageServiceが発行する。
            "photos": [{"s3_object_key": "...", "url": "https://...", "download_url": "https://..."}],
        }}

    service.save_analysis_result(
        report_id=int,
        result=dict,
        user_id=int | str,
    ) -> int | None

事前に入力担当側で session['report_id']（ログイン利用時）または
session['guest_analysis']（未ログイン利用時）をセットする。
ログイン時の利用者IDは Flask-Login の current_user から取得する。
サービスは必ず report_id の所有者確認を行うこと。
"""

from __future__ import annotations

from typing import Any

from flask_login import current_user
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError

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


class InvalidAnalysisResult(ValueError):
    """分析サービスからの応答形式が正しくない。"""


def _csrf_token() -> str:
    """アプリ全体で有効なFlask-WTFと同じCSRFトークンを返す。"""
    return generate_csrf()


def _validate_csrf() -> None:
    """全体CSRF保護と同じ署名・期限・セッションの検証を行う。"""
    submitted = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    try:
        validate_csrf(submitted)
    except ValidationError:
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
        # Flask-Loginが認証した利用者だけを採用する。旧sessionのuser_idは信用しない。
        if not current_user.is_authenticated:
            return None
        return {
            "report_id": report_id,
            "guest_analysis": None,
            "user_id": current_user.user_id,
        }
    if isinstance(guest, dict) and guest:
        return {"report_id": None, "guest_analysis": guest, "user_id": None}
    return None


def _followup_identity() -> dict[str, Any] | None:
    """追加質問を開始した認証ユーザー・分析対象の組を表す。"""
    context = _input_context()
    if context is None:
        return None
    return {
        "report_id": context["report_id"],
        "user_id": context["user_id"],
        # ゲスト分析でも、ログイン状態をまたいで内容を引き継がせない。
        "login_user_id": str(current_user.user_id) if current_user.is_authenticated else None,
    }


def _clear_followup_state() -> None:
    """他ユーザーの追加質問と回答履歴が再利用されないよう破棄する。"""
    for key in (
        "analysis_followup", "analysis_followup_context", "analysis_answers",
        "analysis_reply", "analysis_resume_pending",
    ):
        session.pop(key, None)


def _followup_state_is_owned() -> bool:
    """追加質問の開始時に固定した利用者・分析対象と照合する。"""
    identity = _followup_identity()
    return identity is not None and session.get("analysis_followup_context") == identity


def _service() -> Any:
    service = current_app.extensions.get("damage_analysis_service")
    if service is None:
        raise RuntimeError("DamageAnalysisService が未登録です")
    return service


def _validate_result(result: Any) -> dict[str, Any]:
    """サービスと同じデータ形式を検証し、未検証の結果をSessionへ保存しない。"""
    from .damage_analysis_service import DamageAnalysisService

    try:
        return DamageAnalysisService._validate_result(result)
    except (TypeError, ValueError) as exc:
        raise InvalidAnalysisResult(str(exc)) from exc


def _process_analysis(*, after_followup_answer: bool = False) -> str:
    """分析を行う。回答直後は再判定のみ実施し、再分析を画面遷移後へ分ける。"""
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
        response = service.analyze_damage(
            report_id=context["report_id"],
            guest_analysis=context["guest_analysis"],
            answers=answers,
            user_id=context["user_id"],
            check_followup_only=after_followup_answer,
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
            # ログアウト・ユーザー切替後の旧質問/回答へのアクセスを禁止する。
            session["analysis_followup_context"] = _followup_identity()
            session.pop("analysis_error", None)
            return "analysis.followup"

        if status == "ready_to_resume" and after_followup_answer:
            # 回答内容の再判定が完了。AI分析自体は分析中画面への遷移後に行う。
            reply = response.get("message")
            if not isinstance(reply, str) or not reply.strip():
                raise InvalidAnalysisResult("回答確認メッセージがありません")
            session["analysis_reply"] = reply.strip()[:1000]
            session["analysis_resume_pending"] = True
            session.pop("analysis_followup", None)
            session.pop("analysis_error", None)
            return "analysis.followup"

        if status == "completed":
            if after_followup_answer:
                raise InvalidAnalysisResult("再判定中に結果生成が実行されました")
            result = _validate_result(response.get("result"))
            # ダミーは表示確認のみ。ログイン利用者でもDB保存しない。
            if context["report_id"] is not None and result.get("is_mock") is not True:
                analysis_id = service.save_analysis_result(
                    report_id=context["report_id"],
                    result=result,
                    user_id=context["user_id"],
                )
                if analysis_id is not None:
                    session["analysis_id"] = analysis_id
            session["analysis_result"] = result
            # 認証ユーザー・分析対象が変わった後に旧結果を表示させない。
            session["analysis_result_context"] = {
                "report_id": context["report_id"],
                "user_id": context["user_id"],
            }
            _clear_followup_state()
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

    # 追加回答後は分析中画面に戻って分析を再開する。
    # この経路で回答履歴を消すと、同じ追加質問を繰り返してしまう。
    if request.args.get("resume") == "1" and session.get("analysis_resume_pending") is True:
        if not _followup_state_is_owned():
            _clear_followup_state()
            return redirect(url_for("analysis.index"))
        session.pop("analysis_resume_pending", None)
        session.pop("analysis_reply", None)
    else:
        # 被害状況入力画面から新しく開始したときのみ分析状態を初期化する。
        for key in (
            "analysis_answers", "analysis_followup", "analysis_result",
            "analysis_error", "analysis_id", "analysis_reply", "analysis_resume_pending",
            "analysis_result_context", "analysis_followup_context",
        ):
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
    # 旧利用者の回答履歴が新しい分析に混入しないようにする。
    if (session.get("analysis_followup") or session.get("analysis_resume_pending")
            or session.get("analysis_answers")) and not _followup_state_is_owned():
        _clear_followup_state()
    if session.get("analysis_followup"):
        abort(409, description="追加質問への回答が必要です。")
    if isinstance(session.get("analysis_result"), dict):
        context = _input_context()
        if session.get("analysis_result_context") == {
            "report_id": context["report_id"], "user_id": context["user_id"]
        }:
            return _respond_with_destination("analysis.result")
        # 他のユーザーや別の分析対象の結果を再利用しない。
        session.pop("analysis_result", None)
        session.pop("analysis_result_context", None)
    return _respond_with_destination(_process_analysis())


@analysis_bp.route("/followup", methods=["GET", "POST"])
def followup():
    """追加質問画面の表示と回答受付。"""
    pending = session.get("analysis_followup")
    reply = session.get("analysis_reply") if session.get("analysis_resume_pending") is True else None
    if pending or reply:
        if not _followup_state_is_owned():
            _clear_followup_state()
            if request.method == "POST":
                abort(403, description="追加質問の利用者または分析対象が変わりました。")
            return redirect(url_for("analysis.index"))
    if request.method == "GET" and isinstance(reply, str) and reply:
        return render_template(
            "analysis/analysis_additional_chat.html",
            question=None,
            answers=session.get("analysis_answers", []),
            reply=reply,
            resume_url=url_for("analysis.index", resume="1"),
            csrf_token=_csrf_token(),
            answer_url=url_for("analysis.followup"),
            error=None,
        )
    if not isinstance(pending, dict) or not pending.get("question"):
        if request.method == "POST" and reply:
            abort(409, description="回答は受付済みです。分析の再開をお待ちください。")
        return redirect(url_for("analysis.index"))

    if request.method == "GET":
        return render_template(
            "analysis/analysis_additional_chat.html",
            question=pending["question"],
            answers=session.get("analysis_answers", []),
            reply=None,
            resume_url=None,
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
            reply=None,
            resume_url=None,
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
    return _respond_with_destination(_process_analysis(after_followup_answer=True))


@analysis_bp.get("/result")
def result():
    """GET /analysis/result : 完了した分析結果を表示する。"""
    data = session.get("analysis_result")
    context = _input_context()
    if (not isinstance(data, dict) or context is None or
            session.get("analysis_result_context") != {
                "report_id": context["report_id"], "user_id": context["user_id"]
            }):
        return redirect(url_for("analysis.index"))
    return render_template("analysis/analysis_result.html", result=data,
                           result_chat_url=url_for("chat.show_user_chat"))


@analysis_bp.get("/failure")
def failure():
    """GET /analysis/failure : 分析失敗画面を表示する。"""
    message = session.get("analysis_error", "分析を完了できませんでした。")
    return render_template("analysis/analysis_failure.html", error_message=message)
