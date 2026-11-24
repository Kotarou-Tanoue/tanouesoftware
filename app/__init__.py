import os
from pathlib import Path

from cachelib.file import FileSystemCache
from flask import Flask, render_template

from .config import Config
from .extensions import csrf, db, login_manager, migrate, oauth, server_session
from .models import User


# ログインマネージャー
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app():
    app = Flask(__name__)

    # config.pyの設定を読み込む
    app.config.from_object(Config)

    # CSRF対策を有効化
    csrf.init_app(app)

    # Flask-Loginを初期化
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    # セッションデータの保存先を準備
    session_dir = Path(app.instance_path) / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)

    app.config["SESSION_CACHELIB"] = FileSystemCache(
        cache_dir=str(session_dir),
        threshold=500,
    )

    # 拡張機能の初期化
    db.init_app(app)
    migrate.init_app(app, db)
    # modelsの読み込み
    from app import models

    server_session.init_app(app)

    # OAuthを初期化
    oauth.init_app(app)

    # LINEログインを登録
    oauth.register(
        name="line",
        client_id=app.config["LINE_CHANNEL_ID"],
        client_secret=app.config["LINE_CHANNEL_SECRET"],
        server_metadata_url=("https://access.line.me/.well-known/openid-configuration"),
        client_kwargs={
            "scope": "openid profile",
        },
    )

    from .analysis.analysis_routes import analysis_bp
    from .analysis.chat_routes import chat_bp

    app.register_blueprint(analysis_bp)
    app.register_blueprint(chat_bp)

    # 仮置きマイページのやつ
    from app.mypage import mypage_bp

    app.register_blueprint(mypage_bp, url_prefix="/mypage")

    # 仮置き履歴一覧のやつ
    from app.history import history_bp

    app.register_blueprint(history_bp, url_prefix="/history")
    
    
    # 実APIは明示的に有効化したときのみ登録。Mockのデフォルト動作を維持する。
    use_mock = os.environ.get("ANALYSIS_USE_MOCK") == "1"
    use_live = os.environ.get("ANALYSIS_USE_GEMINI") == "1"
    if use_mock and use_live:
        raise RuntimeError("ANALYSIS_USE_MOCKとANALYSIS_USE_GEMINIを同時に有効化できません。")
    if (use_mock and (app.debug or os.environ.get("FLASK_DEBUG") == "1")) or use_live:
        from .analysis.chat_service import ChatService
        from .analysis.damage_analysis_service import DamageAnalysisService
        from .analysis.gemini_service import GeminiService

        gemini_service = GeminiService(use_mock=not use_live)
        app.extensions["damage_analysis_service"] = DamageAnalysisService(
            gemini_service
        )
        app.extensions["chat_service"] = ChatService(gemini_service)

    # Blueprintの登録
    """
    作成前のため、コメントアウト
    """
    from app.building import building_bp

    app.register_blueprint(building_bp, url_prefix="/building")
    
   
    # トップページ
    @app.route("/")
    def index():
        return render_template("index.html")

    # 認証
    from .auth.auth_routes import auth_bp

    app.register_blueprint(auth_bp)

    # 分析入力(建物情報入力・被害状況入力)
    from .analysis_input.views import analysis_input_bp

    from .analysis_input.views import analysis_input_bp

    app.register_blueprint(analysis_input_bp)

    # 開発中: 写真の保存先(S3)ができるまで、ローカル(instance/uploads)に保存する。
    if "photo_storage_service" not in app.extensions:
        from .analysis_input.local_photo_storage import LocalPhotoStorage

        app.extensions["photo_storage_service"] = LocalPhotoStorage(
            Path(app.instance_path) / "uploads"
        )

    from .common.photos import photo_bp

    app.register_blueprint(photo_bp)

    return app

