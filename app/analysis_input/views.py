# app/analysis_input/views.py
"""分析入力(建物情報入力 → 被害状況入力)のルート。"""
from datetime import datetime

from flask import (
    Blueprint,
    abort,
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
from .forms import BuildingForm, ExistingBuildingForm

analysis_input_bp = Blueprint("analysis_input", __name__, url_prefix="/analysis-input")

# セッションのキー。中身の例:
#   ログイン時   : {"building_id": 5}
#   非ログイン時 : {"building_data": {"building_name": "自宅", "built_year": 2011, ...}}
#   (被害状況入力を作るとき、ここに "damage_data" を足す)
SESSION_KEY = "analysis_input"


# ----------------------------------------------------------------------
# 補助関数
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
        "analysis_input/building.html",
        new_form=new_form,
        existing_form=existing_form,
    )


# ----------------------------------------------------------------------
# ステップ2: 被害状況入力(仮。ここから先を作る)
# ----------------------------------------------------------------------
@analysis_input_bp.route("/damage", methods=["GET", "POST"])
def damage():
    building_info = get_selected_building()
    if building_info is None:
        # ステップ1を飛ばしてきた場合は戻す
        return redirect(url_for("analysis_input.building"))

    # TODO: DamageForm を作り、入力値を session[SESSION_KEY]["damage_data"] に保存する
    # 動作確認用に、選ばれた建物の内容をそのまま表示しておく(text/plainなのでXSSの心配なし)
    return str(building_info), 200, {"Content-Type": "text/plain; charset=utf-8"}