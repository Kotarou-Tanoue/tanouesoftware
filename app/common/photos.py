# app/common/photos.py
"""写真の表示用ルート(アクセス制御つき)と、画面で写真を出すための補助関数。

写真ファイルは instance/ 以下にあり、URLから直接は開けない。
画面に表示するときは、テンプレートで photo_url(キー) を使う。
  <img src="{{ photo_url(key) }}">
表示ルートは「その写真の持ち主」だけに返す(他の人には404)。

S3に移すときは、photo_url() を署名付きURLを返す関数に置き換えればよい。
"""
from __future__ import annotations

import os

from flask import Blueprint, Response, abort, current_app, session, url_for
from flask_login import current_user

from app.extensions import db
from app.models.building import Building
from app.models.damage_location import DamageLocation
from app.models.damage_photo import DamagePhoto
from app.models.damage_report import DamageReport

photo_bp = Blueprint("photos", __name__)

MIMETYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


# ----------------------------------------------------------------------
# テンプレートで使う関数
# ----------------------------------------------------------------------
@photo_bp.app_template_global("photo_url")
def photo_url(key):
    """写真のキー(s3_object_key) → 表示用のURL。テンプレートから photo_url(key) で呼べる。"""
    return url_for("photos.show", key=key)


# ----------------------------------------------------------------------
# 写真のキーを取り出す補助関数(各画面の views.py から呼ぶ)
# ----------------------------------------------------------------------
def _current_user_id():
    return current_user.user_id if current_user.is_authenticated else None


def _owned_photos(user_id, *columns):
    """user_id の建物に属する写真を取り出すクエリ(他人の写真は出てこない)。"""
    return (
        db.session.query(*columns)
        .select_from(DamagePhoto)
        .join(DamageLocation, DamagePhoto.location_id == DamageLocation.location_id)
        .join(DamageReport, DamageLocation.report_id == DamageReport.report_id)
        .join(Building, DamageReport.building_id == Building.building_id)
        .filter(Building.user_id == user_id)
    )


def get_photo_keys_for_report(report_id, user_id):
    """分析(report_id)に使った写真すべてのキーを、登録順で返す。
    分析履歴詳細画面などで使う。user_id の持ち物でなければ空のリスト。"""
    rows = (
        _owned_photos(user_id, DamagePhoto.s3_object_key)
        .filter(DamageReport.report_id == report_id)
        .order_by(DamagePhoto.photo_id)
        .all()
    )
    return [key for (key,) in rows]


def get_first_photo_keys(report_ids, user_id):
    """複数の分析について、それぞれの1枚目の写真のキーを返す: {report_id: キー}
    写真がない分析は含まれない。分析履歴一覧画面・マイページで使う。"""
    report_ids = list(report_ids)
    if not report_ids:
        return {}
    rows = (
        _owned_photos(user_id, DamageReport.report_id, DamagePhoto.s3_object_key)
        .filter(DamageReport.report_id.in_(report_ids))
        .order_by(DamagePhoto.photo_id)
        .all()
    )
    first_keys = {}
    for report_id, key in rows:
        first_keys.setdefault(report_id, key)  # 登録順に並べているので、最初に出たものが1枚目
    return first_keys


def get_current_analysis_photo_keys():
    """いま分析している(分析結果画面に出す)写真すべてのキーを返す。
    ログイン時はDBから、未ログイン時はセッションから取り出す。"""
    user_id = _current_user_id()
    report_id = session.get("report_id")
    if user_id is not None and report_id is not None:
        try:
            return get_photo_keys_for_report(int(report_id), user_id)
        except (TypeError, ValueError):
            return []

    guest = session.get("guest_analysis")
    if isinstance(guest, dict):
        photos = guest.get("photos")
        if isinstance(photos, list):
            return [
                p["s3_object_key"]
                for p in photos
                if isinstance(p, dict) and isinstance(p.get("s3_object_key"), str)
            ]
    return []


# ----------------------------------------------------------------------
# 写真の表示ルート
# ----------------------------------------------------------------------
def _session_photo_keys():
    """このセッションで入力中・分析中の写真のキー(未ログイン利用者、入力途中の写真用)。"""
    keys = set()

    state = session.get("analysis_input")
    if isinstance(state, dict):
        damage = state.get("damage_data")
        locations = damage.get("locations") if isinstance(damage, dict) else None
        for entry in locations if isinstance(locations, list) else []:
            photo_keys = entry.get("photo_keys") if isinstance(entry, dict) else None
            if isinstance(photo_keys, list):
                keys.update(k for k in photo_keys if isinstance(k, str))

    keys.update(get_current_analysis_photo_keys())
    return keys


def _is_owned_by_current_user(key):
    user_id = _current_user_id()
    if user_id is None:
        return False
    found = (
        _owned_photos(user_id, DamagePhoto.photo_id)
        .filter(DamagePhoto.s3_object_key == key)
        .first()
    )
    return found is not None


@photo_bp.get("/photo-files/<path:key>")
def show(key):
    """GET /photo-files/<キー> : 写真の持ち主(またはそのセッションの利用者)にだけ画像を返す。"""
    # 持ち主でなければ、存在するかどうかも分からないよう、403ではなく404を返す
    if key not in _session_photo_keys() and not _is_owned_by_current_user(key):
        abort(404)

    mimetype = MIMETYPES.get(os.path.splitext(key)[1].lower())
    service = current_app.extensions.get("photo_storage_service")
    if mimetype is None or service is None:
        abort(404)

    try:
        data = service.read_photo(key)
    except Exception:
        current_app.logger.warning("写真を読み込めませんでした: %s", key, exc_info=True)
        abort(404)

    response = Response(data, mimetype=mimetype)
    response.headers["Cache-Control"] = "private, max-age=3600"  # 共有キャッシュには残さない
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
