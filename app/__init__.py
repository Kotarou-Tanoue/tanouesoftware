import os
from pathlib import Path

from cachelib.file import FileSystemCache
from flask import Flask, render_template

from .config import Config
from .extensions import csrf, db, migrate, server_session


def create_app():
    app = Flask(__name__)

    # config.pyの設定を読み込む
    app.config.from_object(Config)

    # CSRF対策を有効化
    csrf.init_app(app)

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

    from .analysis.analysis_routes import analysis_bp

    app.register_blueprint(analysis_bp)

    # 開発中のみダミーのGeminiServiceを使用。実際の被害判定は行わない。
    # 本物のGeminiService完成後にこの登録部分を差し替える。
    if os.environ.get("ANALYSIS_USE_MOCK") == "1" and app.debug:
        from .analysis.damage_analysis_service import DamageAnalysisService
        from .analysis.gemini_service import GeminiService

        app.extensions["damage_analysis_service"] = DamageAnalysisService(
            GeminiService()
        )

    # Blueprintの登録
    """
    作成前のため、コメントアウト
    from app.building import building_bp

    app.register_blueprint(building_bp, url_prefix="/building")
    """

    # トップページ
    @app.route("/")
    def index():
        return render_template("index.html")

    # 認証
    from .auth.login import login_bp
    from .auth.logout import logout_bp

    app.register_blueprint(login_bp)
    app.register_blueprint(logout_bp)

    return app
