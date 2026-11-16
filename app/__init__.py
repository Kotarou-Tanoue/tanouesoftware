from pathlib import Path

from cachelib.file import FileSystemCache
from flask import Flask, render_template

from .config import Config
from .extensions import db, migrate, server_session


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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
    server_session.init_app(app)

    from .analysis.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp)

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

    return app
