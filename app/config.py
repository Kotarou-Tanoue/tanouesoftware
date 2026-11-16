import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# プロジェクト直下の.envを読み込む
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # アプリの秘密鍵
    SECRET_KEY = os.environ["SECRET_KEY"]

    # データベース
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # セッションの保存方式
    SESSION_TYPE = "cachelib"
    SESSION_SERIALIZATION_FORMAT = "json"

    # セッションの有効期限
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # セッションCookie
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )
