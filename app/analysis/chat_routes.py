"""結果質問画面の ChatView（設計: GET /chat、POST /chat/message）。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import (
    Blueprint, abort, current_app, jsonify, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from app.extensions import db
from app.models import AnalysisHistory
from .analysis_routes import _input_context
from .chat_service import MAX_CHAT_QUESTION_LENGTH


chat_bp = Blueprint("chat", __name__)


def _service():
    service = current_app.extensions.get("chat_service")
    if service is None:
        # 実AI未接続の環境で、回答を生成したかのように偽装しない。
        abort(503, description="AI質問サービスが準備されていません。")
    return service


def _session_analysis_scope() -> dict[str, Any] | None:
    """現在の分析結果を元の利用者・分析対象と照合する。"""
    result = session.get("analysis_result")
    identity = session.get("analysis_result_context")
    context = _input_context()
    if not isinstance(result, dict) or context is None:
        return None
    if identity != {"report_id": context["report_id"], "user_id": context["user_id"]}:
        return None
    # ゲスト時の結果がログイン後のユーザーに引き継がれないようにする。
    if context["report_id"] is None and current_user.is_authenticated:
        return None
    raw_analysis_id = session.get("analysis_id")
    if (current_user.is_authenticated and context["report_id"] is not None
            and result.get("is_mock") is not True
            and type(raw_analysis_id) is int and raw_analysis_id > 0):
        record = db.session.get(AnalysisHistory, raw_analysis_id)
        if record is not None and record.report_id == context["report_id"]:
            return {
                "kind": "saved", "analysis_id": raw_analysis_id,
                "user_id": int(current_user.user_id),
            }
    digest = hashlib.sha256(json.dumps(
        result, sort_keys=True, ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()
    return {
        "kind": "session", "report_id": context["report_id"],
        "user_id": context["user_id"],
        "login_user_id": str(current_user.user_id) if current_user.is_authenticated else None,
        "result_digest": digest,
    }


def _saved_context(scope: dict[str, Any]):
    """指定分析履歴の本人確認と、AIへの渡し値の生成。"""
    if not current_user.is_authenticated or scope.get("user_id") != int(current_user.user_id):
        abort(403)
    service = _service()
    try:
        record = service._owned_analysis(scope["analysis_id"], int(current_user.user_id))
    except PermissionError:
        abort(404)
    if scope.get("report_id") is not None and record.report_id != scope["report_id"]:
        abort(403)
    analysis_result = {
        "damage_level": record.damage_level,
        "repair_cost_min": record.repair_cost_min,
        "repair_cost_max": record.repair_cost_max,
        "description": record.description,
    }
    return analysis_result, service.get_chat_history(record.analysis_id, int(current_user.user_id))


def _active_context(scope: dict[str, Any]):
    """POST時にも保存したチャット対象と現時点の認証を再照合する。"""
    if scope.get("kind") == "saved":
        return _saved_context(scope)
    if scope.get("kind") != "session" or _session_analysis_scope() != scope:
        abort(403)
    return session["analysis_result"], []


def _chat_messages(scope: dict[str, Any], stored: list[dict[str, str]]):
    if session.get("chat_scope") != scope:
        session["chat_scope"] = scope
        session.pop("chat_session_messages", None)
        session.pop("chat_error", None)
    messages = session.get("chat_session_messages", [])
    if not isinstance(messages, list):
        messages = []
    return stored + messages


def _get_request_scope():
    raw = request.args.get("analysis_id")
    if raw is not None:
        if not raw.isdecimal() or int(raw) <= 0:
            abort(400)
        if not current_user.is_authenticated:
            abort(403)
        return {"kind": "saved", "analysis_id": int(raw), "user_id": int(current_user.user_id)}
    return _session_analysis_scope()


@chat_bp.get("/chat")
def show_user_chat():
    """分析結果または所有する分析履歴から結果質問画面を表示する。"""
    scope = _get_request_scope()
    if scope is None:
        return redirect(url_for("index"))
    result, stored = _active_context(scope)
    messages = _chat_messages(scope, stored)
    error = session.pop("chat_error", None)
    has_current_result = _session_analysis_scope() is not None
    return render_template(
        "analysis/analysis_user_chat.html",
        messages=messages, error=error, is_mock=_service().is_mock,
        csrf_token=generate_csrf(),
        send_url=url_for("chat.send_message"),
        back_url=url_for("analysis.result") if has_current_result else url_for("index"),
        back_label="分析結果に戻る" if has_current_result else "ホームに戻る",
    )


@chat_bp.post("/chat/message")
def send_message():
    """質問受付、AI回答生成、認証済みの正式な履歴のみDBに保存。"""
    scope = session.get("chat_scope")
    if not isinstance(scope, dict):
        abort(403, description="先に結果質問画面を開いてください。")
    analysis_result, stored = _active_context(scope)
    question = request.form.get("question")
    if request.is_json:
        payload = request.get_json(silent=True)
        question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not (1 <= len(question.strip()) <= MAX_CHAT_QUESTION_LENGTH):
        session["chat_error"] = "質問を1～2000文字以内で入力してください。"
        return _reply(scope, 400)
    question = question.strip()
    messages = _chat_messages(scope, stored)
    service = _service()
    try:
        answer = service.process_chatbot(question, analysis_result, messages)
        # 本物の分析履歴IDがあるログイン利用者だけがDB保存対象。
        if scope["kind"] == "saved" and not service.is_mock:
            service.save_message(scope["analysis_id"], scope["user_id"], question, answer)
        else:
            ephemeral = session.get("chat_session_messages", [])
            ephemeral.append({"question": question, "answer": answer})
            # セッションの過大化を防止。DB保存済みの履歴は別途取得する。
            session["chat_session_messages"] = ephemeral[-30:]
    except TimeoutError:
        current_app.logger.warning("結果質問のAI応答がタイムアウトしました")
        session["chat_error"] = "回答の生成に時間がかかっています。しばらくしてからもう一度お試しください。"
        return _reply(scope, 504)
    except Exception:
        current_app.logger.exception("結果質問の生成・保存に失敗しました")
        session["chat_error"] = "回答を取得できませんでした。しばらくしてからもう一度お試しください。"
        return _reply(scope, 503)
    return _reply(scope, 200, answer)


def _reply(scope: dict[str, Any], status: int, answer: str | None = None):
    if request.is_json or request.accept_mimetypes.best == "application/json":
        if answer is not None:
            return jsonify({"answer": answer}), 200
        return jsonify({"error": session.get("chat_error", "回答を取得できませんでした。")}), status
    params = {"analysis_id": scope["analysis_id"]} if scope["kind"] == "saved" else {}
    return redirect(url_for("chat.show_user_chat", **params), code=303)
