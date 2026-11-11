import os
from datetime import timedelta

from cachelib.file import FileSystemCache
from flask import Flask, render_template
from flask_session import Session


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SESSION_TYPE"] = "cachelib"
    app.config["SESSION_SERIALIZATION_FORMAT"] = "json"
    app.config["SESSION_PERMANENT"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )

    session_dir = os.path.join(app.instance_path, "sessions")
    os.makedirs(session_dir, exist_ok=True)

    app.config["SESSION_CACHELIB"] = FileSystemCache(
        cache_dir=session_dir,
        threshold=500,
    )

    Session(app)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
