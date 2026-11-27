# app/analysis_input/views.py
"""分析入力(建物情報入力 → 被害状況入力)のルート。"""
import os
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.building import Building
from app.models.damage_location import DamageLocation
from app.models.damage_photo import DamagePhoto
from app.models.damage_report import DamageReport
from app.models.damage_status import DamageStatus
from app.models.earthquake_relation import EarthquakeRelation  # ★クラス名は要確認
from .forms import (
    OTHER_VALUE,
    STATUS_FIELDS,
    BuildingForm,
    BuildingStatusForm,
    DamageEntryForm,
    ExistingBuildingForm,
)

analysis_input_bp = Blueprint("analysis_input", __name__, url_prefix="/analysis-input")

# セッションのキー。中身の例:
#   {
#     "building_id": 5,                      # ログイン時(どちらか片方)
#     "building_data": {...},                # 非ログイン時(どちらか片方)
#     "damage_data": {                       # ステップ2の入力内容
#         "locations": [ {"location_name": "和室", ..., "photo_keys": [...]}, ... ],
#         "status": {"door_window_status": 1, "noise_status": 0, "tilt_status": 2},
#     },
#   }
SESSION_KEY = "analysis_input"

# ステップ2の制限
MAX_DAMAGE_ENTRIES = 20            # 被害情報の登録上限(件)
MAX_PHOTOS_PER_ENTRY = 5           # 1件の被害情報に付けられる写真の上限(枚)
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 写真1枚の上限(10MB。分析側の上限と同じ)
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


# ----------------------------------------------------------------------
# 補助関数(共通)
# ----------------------------------------------------------------------
def get_login_user_id():
    """ログイン中なら利用者ID、未ログインならNoneを返す。
    ログイン判定はこの関数に閉じ込めてあるので、認証まわりを変えるときはここだけ直す。"""
    return current_user.user_id if current_user.is_authenticated else None


def _building_to_dict(b):
    """Buildingモデル → dict。セッション保存時(BuildingForm.to_dict)と同じキーにそろえる。"""
    return {
        "building_name": b.building_name,
        "building_type_code": b.building_type_code,
        "built_year": b.built_year,
        "prefecture": b.prefecture,
        "city": b.city,
    }


# セッションの building_data に必要なキー(BuildingForm.to_dict() のキーと同じ)
BUILDING_KEYS = {"building_name", "building_type_code", "built_year", "prefecture", "city"}


def _get_saved_building_data(state):
    """セッションの building_data を返す。形式が違う(古いデータなど)場合はNone。"""
    data = state.get("building_data")
    if isinstance(data, dict) and BUILDING_KEYS <= data.keys():
        return data
    return None


def _to_form_data(building_data):
    """セッションの building_data → BuildingForm の初期値(戻る操作での再表示用)。
    to_dict() の逆変換: 建築年 → 築年数、種類コード(int) → 文字列。"""
    return {
        "name": building_data["building_name"],
        "building_type": str(building_data["building_type_code"]),
        "age_years": max(0, datetime.now().year - building_data["built_year"]),
        "prefecture": building_data["prefecture"],
        "city": building_data["city"],
    }


def _save_building_to_session(*, building_id=None, building_data=None):
    """選んだ建物をセッションに保存する。building_id か building_data のどちらか片方だけ残す。
    被害状況など、他のキー(damage_data)は消さずに残す。"""
    state = dict(session.get(SESSION_KEY, {}))
    state.pop("building_id", None)
    state.pop("building_data", None)
    if building_id is not None:
        state["building_id"] = building_id
    if building_data is not None:
        state["building_data"] = building_data
    session[SESSION_KEY] = state  # 再代入することで変更を確実に保存させる


def _create_building(user_id, data):
    """建物をDBに保存して返す。失敗したらロールバックしてNoneを返す。"""
    try:
        new_building = Building(user_id=user_id, **data)
        db.session.add(new_building)
        db.session.commit()
        return new_building
    except SQLAlchemyError:
        db.session.rollback()
        return None


def get_selected_building():
    """ステップ1で選ばれた建物をdictで返す。なければNone。
    ログイン時(DB)でも非ログイン時(セッション)でも同じ形で返すので、
    被害状況入力や計算担当は出どころを気にしなくてよい。"""
    state = session.get(SESSION_KEY, {})

    building_id = state.get("building_id")
    if building_id is not None:
        user_id = get_login_user_id()
        if not user_id:
            return None  # ログアウト後に古いbuilding_idが残っていても使わせない
        b = Building.query.filter_by(building_id=building_id, user_id=user_id).first()
        return _building_to_dict(b) if b else None

    return _get_saved_building_data(state)


# ----------------------------------------------------------------------
# ステップ1: 建物情報入力
# ----------------------------------------------------------------------
@analysis_input_bp.route("/building", methods=["GET", "POST"])
def building():
    user_id = get_login_user_id()
    state = session.get(SESSION_KEY, {})

    # --- 新規入力フォーム(戻ってきたときは、セッションの値を初期値にする) ---
    saved_data = _get_saved_building_data(state)
    if request.method == "GET" and saved_data:
        new_form = BuildingForm(data=_to_form_data(saved_data))
    else:
        new_form = BuildingForm()

    # --- 登録済みの建物フォーム(ログイン中で、建物が登録済みのときだけ) ---
    existing_form = None
    if user_id:
        buildings = (
            Building.query.options(joinedload(Building.building_type))
            .filter_by(user_id=user_id)
            .order_by(Building.building_id)
            .all()
        )
        if buildings:
            existing_form = ExistingBuildingForm()
            existing_form.set_choices(buildings)  # POSTのときも必須(選択肢が空だと検証が通らない)
            if request.method == "GET" and state.get("building_id"):
                existing_form.building.data = state["building_id"]  # 戻ったとき選択を復元

    # --- A) 登録済みの建物を選んだ場合 ---
    if existing_form and existing_form.submit_existing.data and existing_form.validate_on_submit():
        selected = Building.query.filter_by(
            building_id=existing_form.building.data, user_id=user_id
        ).first()
        if selected is None:  # 選択肢の検証で弾かれるはずだが、念のための二重チェック
            abort(403)
        _save_building_to_session(building_id=selected.building_id)
        return redirect(url_for("analysis_input.damage"))

    # --- B) 新しい建物を入力した場合 ---
    if new_form.submit_new.data and new_form.validate_on_submit():
        data = new_form.to_dict()

        if not user_id:
            # 非ログイン: 内容をセッションに保存
            _save_building_to_session(building_data=data)
            return redirect(url_for("analysis_input.damage"))

        # ログイン: DBに保存し、IDだけセッションに持つ
        created = _create_building(user_id, data)
        if created is not None:
            _save_building_to_session(building_id=created.building_id)
            return redirect(url_for("analysis_input.damage"))
        flash("建物の保存に失敗しました。もう一度お試しください。")

    return render_template(
        "analysis_input/analysis_input_building.html",
        new_form=new_form,
        existing_form=existing_form,
    )


# ----------------------------------------------------------------------
# 補助関数(ステップ2: 被害状況入力)
# ----------------------------------------------------------------------
# セッションの damage_data["locations"] の各要素に必要なキー
ENTRY_KEYS = {"location_name", "location_type", "damage_type", "earthquake_relation", "photo_keys"}


def _get_damage_data(state):
    """セッションの damage_data を安全な形で返す。形式が違うデータは捨てる。"""
    data = state.get("damage_data")
    if not isinstance(data, dict):
        data = {}
    locations = data.get("locations")
    if not isinstance(locations, list):
        locations = []
    locations = [e for e in locations if isinstance(e, dict) and ENTRY_KEYS <= e.keys()]
    status = data.get("status")
    status = dict(status) if isinstance(status, dict) else {}
    return {"locations": locations, "status": status}


def _save_damage_data(damage_data):
    """damage_data をセッションに保存する(建物など他のキーは残す)。"""
    state = dict(session.get(SESSION_KEY, {}))
    state["damage_data"] = damage_data
    session[SESSION_KEY] = state


def _remember_status(damage_data, status_form):
    """建物全体の状態(3問)の入力済みの値を damage_data に残す。
    「追加」「削除」でページが再読み込みされても、入力が消えないようにするため。"""
    for name in STATUS_FIELDS:
        field = getattr(status_form, name)
        valid_values = {value for value, _ in field.choices}
        if field.data and field.data in valid_values:
            damage_data["status"][name] = int(field.data)


def _uploaded_photos():
    """フォームで選ばれた写真(未選択の空ファイルは除く)"""
    return [f for f in request.files.getlist("photos") if f and f.filename]


def _validate_photos(files):
    """写真のチェック。エラーメッセージのリストを返す(問題なければ空)。"""
    errors = []
    if len(files) > MAX_PHOTOS_PER_ENTRY:
        errors.append(f"写真は1回に{MAX_PHOTOS_PER_ENTRY}枚まで追加できます。")
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower().lstrip(".")
        if ext not in ALLOWED_PHOTO_EXTENSIONS:
            errors.append(f"「{f.filename}」は対応していない形式です(JPEG・PNG・WEBPのみ)。")
            continue
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > MAX_PHOTO_BYTES:
            errors.append(f"「{f.filename}」は10MBを超えています。")
    return errors


def _store_photos(files):
    """写真を保存し、S3オブジェクトキーのリストを返す。失敗したらNone。

    PhotoStorageService が未実装の間は、写真は保存されず空のリストを返す。
    サービスができたら app.extensions["photo_storage_service"] に登録すれば、そのまま使える。
    想定するインターフェース: service.upload_photo(file_storage, *, user_id=None) -> str(s3_object_key)
    """
    if not files:
        return []
    service = current_app.extensions.get("photo_storage_service")
    if service is None:
        flash("写真の保存先(S3)がまだ接続されていないため、写真は登録されませんでした。(開発中)")
        return []
    try:
        user_id = get_login_user_id()
        return [service.upload_photo(f, user_id=user_id) for f in files]
    except Exception:
        current_app.logger.exception("写真の保存に失敗しました")
        return None


def _create_report(building_id, damage_data):
    """ログイン時: 被害状況(DamageReport / DamageLocation / DamagePhoto)をDBに保存し、report_id を返す。
    分析ごとに新しい DamageReport を作る(以前の分析の履歴は残る)。"""
    status = damage_data["status"]
    report = DamageReport(
        building_id=building_id,
        door_window_status=status["door_window_status"],
        noise_status=status["noise_status"],
        tilt_status=status["tilt_status"],
    )
    for entry in damage_data["locations"]:
        location = DamageLocation(
            location_name=entry["location_name"],
            location_type=entry["location_type"],
            damage_type=entry["damage_type"],
            earthquake_relation=entry["earthquake_relation"],
        )
        for key in entry["photo_keys"]:
            location.damage_photos.append(DamagePhoto(s3_object_key=key))
        report.damage_locations.append(location)

    db.session.add(report)
    db.session.flush()  # report_id を確定させる
    report_id = report.report_id
    db.session.commit()
    return report_id


def _build_guest_payload(building_info, damage_data):
    """非ログイン時: 分析担当に渡すdict。ログイン時にサービスがDBから作るデータと同じ形にそろえてある。"""
    locations = []
    all_photos = []
    for entry in damage_data["locations"]:
        photos = [{"s3_object_key": key} for key in entry["photo_keys"]]
        locations.append(
            {
                "location_name": entry["location_name"],
                "location_type": entry["location_type"],
                "damage_type": entry["damage_type"],
                "earthquake_relation": entry["earthquake_relation"],
                "description": None,
                "severity": None,
                "photos": photos,
            }
        )
        all_photos.extend(dict(p) for p in photos)
    return {
        "building": dict(building_info),
        "report": dict(damage_data["status"]),
        "locations": locations,
        "photos": all_photos,
    }


def _hand_off_to_analysis(user_id, building_info, damage_data):
    """分析担当(analysis_bp)が読むセッションをセットする。
      ログイン時(建物がDBにある) : session["report_id"] と session["user_id"]
      それ以外                    : session["guest_analysis"]
    DB保存に失敗したら SQLAlchemyError を投げる(呼び出し側で処理する)。"""
    building_id = session.get(SESSION_KEY, {}).get("building_id")

    if user_id and building_id is not None:
        report_id = _create_report(building_id, damage_data)
        session["report_id"] = report_id
        session["user_id"] = user_id  # 分析側が所有者確認に使う(キー名は認証担当と統一すること)
        session.pop("guest_analysis", None)
    else:
        session["guest_analysis"] = _build_guest_payload(building_info, damage_data)
        session.pop("report_id", None)
        session.pop("user_id", None)

    # 分析側に渡し終えたので、入力途中のデータを消す
    session.pop(SESSION_KEY, None)


# ----------------------------------------------------------------------
# ステップ2: 被害状況入力
# ----------------------------------------------------------------------
@analysis_input_bp.route("/damage", methods=["GET", "POST"])
def damage():
    building_info = get_selected_building()
    if building_info is None:
        # ステップ1を飛ばしてきた場合は戻す
        return redirect(url_for("analysis_input.building"))

    user_id = get_login_user_id()
    damage_data = _get_damage_data(session.get(SESSION_KEY, {}))

    # 選択肢のもとになるマスタ
    status_rows = DamageStatus.query.order_by(DamageStatus.status_code).all()
    relation_rows = EarthquakeRelation.query.order_by(EarthquakeRelation.relation_code).all()

    # --- フォームの用意(選択肢のセットはPOSTのときも必須) ---
    status_form = BuildingStatusForm()
    entry_form = DamageEntryForm()
    status_defaults = status_form.set_choices(status_rows)  # 戻り値: 各質問の「わからない」のコード
    relation_default = entry_form.set_relation_choices(relation_rows)

    # 初期値はGETのときだけ入れる(POSTのときはユーザーの入力を優先する)
    if request.method == "GET":
        saved_status = damage_data["status"]
        for name in STATUS_FIELDS:
            getattr(status_form, name).data = str(saved_status.get(name, status_defaults[name] or ""))
        entry_form.earthquake_relation.data = relation_default or ""

    photo_errors = []

    if request.method == "POST":
        delete_index = request.form.get("delete_index")

        # --- 登録済みの被害情報を削除 ---
        if delete_index is not None:
            try:
                index = int(delete_index)
            except ValueError:
                abort(400)
            if 0 <= index < len(damage_data["locations"]):
                del damage_data["locations"][index]
            _remember_status(damage_data, status_form)
            _save_damage_data(damage_data)
            return redirect(url_for("analysis_input.damage"))

        # --- 「＋ この被害情報を追加」 ---
        elif entry_form.submit_add.data:
            files = _uploaded_photos()
            photo_errors = _validate_photos(files)
            if len(damage_data["locations"]) >= MAX_DAMAGE_ENTRIES:
                flash(f"被害情報は{MAX_DAMAGE_ENTRIES}件まで登録できます。")
            elif entry_form.validate_on_submit() and not photo_errors:
                photo_keys = _store_photos(files)
                if photo_keys is None:
                    photo_errors = ["写真の保存に失敗しました。もう一度お試しください。"]
                else:
                    damage_data["locations"].append(entry_form.to_dict(photo_keys))
                    _remember_status(damage_data, status_form)
                    _save_damage_data(damage_data)
                    return redirect(url_for("analysis_input.damage"))

        # --- 「AI分析を開始する」 ---
        elif status_form.submit_analyze.data:
            if _uploaded_photos():
                flash("選択した写真がまだ追加されていません。「この被害情報を追加」を押してから、分析を開始してください。")
            elif not damage_data["locations"]:
                flash("被害情報を1件以上追加してください。")
            elif status_form.validate_on_submit():
                _remember_status(damage_data, status_form)
                _save_damage_data(damage_data)
                try:
                    _hand_off_to_analysis(user_id, building_info, damage_data)
                except SQLAlchemyError:
                    db.session.rollback()
                    current_app.logger.exception("被害状況の保存に失敗しました")
                    flash("被害状況の保存に失敗しました。もう一度お試しください。")
                else:
                    return redirect(url_for("analysis.index"))

    # 登録済み一覧に表示する「地震との関連」の文言(画面のセレクトと同じ文言にする)
    relation_labels = {
        int(code): label for code, label in entry_form.earthquake_relation.choices if code != ""
    }
    return render_template(
        "analysis_input/analysis_input_damage.html",
        entry_form=entry_form,
        status_form=status_form,
        locations=damage_data["locations"],
        relation_labels=relation_labels,
        photo_errors=photo_errors,
        max_photos=MAX_PHOTOS_PER_ENTRY,
        other_value=OTHER_VALUE,
    )