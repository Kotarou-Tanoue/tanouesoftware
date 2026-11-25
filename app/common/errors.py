from flask import render_template


def handle_http_error(error):
    """HTTPエラーに対応するエラーページを返却する。"""

    response = error.get_response()

    response.set_data(render_template(f"errors/{error.code}.html"))

    response.content_type = "text/html; charset=utf-8"

    return response


def register_error_handlers(app):
    """アプリケーションにエラーハンドラーを登録する。"""

    error_codes = (
        400,
        401,
        403,
        404,
        405,
        413,
        429,
        500,
        503,
    )

    for code in error_codes:
        app.register_error_handler(code, handle_http_error)


# テスト用 本番環境では削除
"""
error_test_bp = Blueprint("error_test", __name__)


@error_test_bp.get("/test/error/<int:code>")
def test_error(code):

    allowed_codes = (
        400,
        401,
        403,
        404,
        405,
        413,
        429,
        500,
        503,
    )

    if code not in allowed_codes:
        abort(404)

    abort(code)

"""
# ここまで
