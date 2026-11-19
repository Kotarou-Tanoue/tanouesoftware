import os
from pathlib import Path

from cachelib.file import FileSystemCache
from flask import Flask, render_template

from .config import Config
from .extensions import csrf, db, login_manager, migrate, server_session
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

    from .analysis.analysis_routes import analysis_bp

    app.register_blueprint(analysis_bp)

    #仮置きマイページのやつ
    from app.mypage import mypage_bp

    app.register_blueprint(mypage_bp,url_prefix="/mypage")

    # 開発中のみダミーのGeminiServiceを使用。実際の被害判定は行わない。
    # 本物のGeminiService完成後にこの登録部分を差し替える。
    if os.environ.get("ANALYSIS_USE_MOCK") == "1" and (
        app.debug or os.environ.get("FLASK_DEBUG") == "1"
    ):
        from .analysis.damage_analysis_service import DamageAnalysisService
        from .analysis.gemini_service import GeminiService

        app.extensions["damage_analysis_service"] = DamageAnalysisService(
            GeminiService()
        )

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

    app.register_blueprint(analysis_input_bp)


    return app

