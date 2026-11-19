import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

from app.auth.line_auth_service import (
    LINE_AUTHORIZE_URL,
    LineAuthError,
    get_or_create_line_user,
    verify_line_login,
)
from app.models.user import User

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)
LINE_FLOW_KEY = "line_login_flow"
LINE_FLOW_TTL = 600


# ログインページ
@auth_bp.route("/login")
def login():
    return render_template("auth/login.html")


def _line_configured():
    return all(
        current_app.config.get(key)
        for key in (
            "LINE_CHANNEL_ID",
            "LINE_CHANNEL_SECRET",
            "LINE_CALLBACK_URL",
        )
    )


def _line_failure(
    message="LINEログインを完了できませんでした。もう一度お試しください。",
):
    flash(message)
    return redirect(url_for("auth.login"), code=303)


@auth_bp.after_request
def protect_line_response(response):
    if request.endpoint in {"auth.line_login", "auth.line_callback"}:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@auth_bp.get("/line")
def line_login():
    if not _line_configured():
        return _line_failure("LINEログインは現在利用できません。")

    state = secrets.token_hex(32)
    nonce = secrets.token_hex(32)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    session[LINE_FLOW_KEY] = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "issued_at": time.time(),
    }
    params = urlencode(
        {
            "response_type": "code",
            "client_id": current_app.config["LINE_CHANNEL_ID"],
            "redirect_uri": current_app.config["LINE_CALLBACK_URL"],
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return redirect(f"{LINE_AUTHORIZE_URL}?{params}")


@auth_bp.get("/line/callback")
def line_callback():
    flow = session.get(LINE_FLOW_KEY)
    states = request.args.getlist("state")
    if (
        not flow
        or len(states) != 1
        or not secrets.compare_digest(
            states[0].encode("utf-8"), flow["state"].encode("ascii")
        )
    ):
        return _line_failure()
    session.pop(LINE_FLOW_KEY)
    if time.time() - flow["issued_at"] > LINE_FLOW_TTL or not _line_configured():
        return _line_failure()

    errors = request.args.getlist("error")
    codes = request.args.getlist("code")
    if errors == ["access_denied"] and not codes:
        return _line_failure("LINEログインがキャンセルされました。")
    if errors or len(codes) != 1 or not codes[0]:
        return _line_failure()

    try:
        line_user_id = verify_line_login(codes[0], flow["nonce"], flow["verifier"])
        user = get_or_create_line_user(line_user_id)
        if not user.is_active:
            return _line_failure()
        session.clear()
        login_user(user)
        current_app.session_interface.regenerate(session)
    except (LineAuthError, RequestException, SQLAlchemyError, ValueError) as exc:
        current_app.logger.warning("LINE login failed (%s)", type(exc).__name__)
        return _line_failure()

    return redirect(url_for("index"), code=303)


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
        session.clear()
        return redirect(url_for("index"))

    if not current_user.is_authenticated:
        return render_template("auth/login.html")

    return render_template("auth/logout.html")
