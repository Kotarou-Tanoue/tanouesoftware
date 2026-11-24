"""LINE LoginのIDトークン検証と利用者の照合・登録。"""

import re

import requests
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.provider import Provider
from app.models.user import User
from app.models.user_auth import UserAuth

LINE_AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
LINE_ISSUER = "https://access.line.me"
LINE_PROVIDER_CODE = 1  # database/seed_master.sql
USER_ROLE_CODE = 1


# LINE認証や認証マスタの検証に失敗したことを表す、独自の例外クラス
class LineAuthError(Exception):
    """LINE認証または認証マスタの検証に失敗した。"""


# LINE APIにPOSTリクエストを送信し、レスポンスが正常であることを確認したうえで、取得したJSONデータを辞書型として返す共通関数
def _post_to_line(url, data):
    response = requests.post(url, data=data, timeout=(3, 7), allow_redirects=False)
    if response.status_code != 200:
        raise LineAuthError("LINE API rejected the request")
    payload = response.json()
    if not isinstance(payload, dict):
        raise LineAuthError("Invalid LINE API response")
    return payload


def verify_line_login(code, nonce, code_verifier):
    """認可コードを交換し、LINEの検証APIが返した利用者IDを取得する。"""
    config = current_app.config
    token = _post_to_line(
        LINE_TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config["LINE_CALLBACK_URL"],
            "client_id": config["LINE_CHANNEL_ID"],
            "client_secret": config["LINE_CHANNEL_SECRET"],
            "code_verifier": code_verifier,
        },
    )
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise LineAuthError("Missing LINE ID token")

    claims = _post_to_line(
        LINE_VERIFY_URL,
        {
            "id_token": id_token,
            "client_id": config["LINE_CHANNEL_ID"],
            "nonce": nonce,
        },
    )
    if (
        claims.get("iss") != LINE_ISSUER
        or claims.get("aud") != config["LINE_CHANNEL_ID"]
        or claims.get("nonce") != nonce
    ):
        raise LineAuthError("Invalid LINE ID token claims")
    return claims.get("sub")


def _find_line_user(line_user_id):
    provider = db.session.get(Provider, LINE_PROVIDER_CODE)
    if provider is None or provider.provider_name.strip().casefold() != "line":
        raise LineAuthError("LINE provider master is missing or mismatched")

    identity = db.session.get(UserAuth, (LINE_PROVIDER_CODE, line_user_id))
    if identity is None:
        return None
    # MySQLの照合順序による大文字小文字などの同一視を避ける。
    if identity.provider_user_id != line_user_id or identity.user is None:
        raise LineAuthError("Invalid stored LINE identity")
    return identity.user


def get_or_create_line_user(line_user_id):
    """検証済みsubで照合し、初回のみ利用者と認証情報を一括登録する。"""
    if not isinstance(line_user_id, str) or not re.fullmatch(
        r"U[0-9a-f]{32}", line_user_id
    ):
        raise LineAuthError("Invalid LINE subject")

    try:
        user = _find_line_user(line_user_id)
        if user is not None:
            return user
        user = User(role_code=USER_ROLE_CODE)
        db.session.add(user)
        db.session.add(
            UserAuth(
                provider_code=LINE_PROVIDER_CODE,
                provider_user_id=line_user_id,
                user=user,
            )
        )
        db.session.commit()
        return user
    except IntegrityError:
        # 同時登録の勝者を新しいトランザクションで照合する。
        db.session.rollback()
        try:
            user = _find_line_user(line_user_id)
            if user is not None:
                return user
        except Exception:
            db.session.rollback()
            raise
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise
