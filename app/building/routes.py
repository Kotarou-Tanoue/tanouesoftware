
from datetime import datetime

from flask import render_template, request, redirect, url_for, abort, flash, session
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Building

from . import building_bp

BUILDING_TYPE_NAMES = {1: "戸建て", 2: "集合住宅"}

# 建物登録
@building_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "POST":
        name = request.form["building-name"].strip()
        btype = int(request.form["building-type"])
        age = int(request.form["building-age"])
        prefecture = request.form["prefecture"]
        city = request.form["city"].strip()

        # 築年数から建築年を計算
        built_year = datetime.now().year - age

        # Buildingモデルを使って登録データを作成
        building = Building(
            user_id=current_user.user_id,
            building_name=name,
            building_type_code=btype,
            built_year=built_year,
            prefecture=prefecture,
            city=city,
        )

        # DBに保存
        db.session.add(building)
        db.session.commit()

        return redirect(url_for("building.register_complete"))

    return render_template("building/building_register.html")


# 建物登録完了
@building_bp.route("/register/complete")
@login_required
def register_complete():
    return render_template("building/building_register_complete.html")


# 建物詳細
# 建物詳細
@building_bp.route("/detail/<int:building_id>")
@login_required
def detail(building_id):

    building = Building.query.filter_by(
        building_id=building_id,
        user_id=current_user.user_id
    ).first_or_404()

    building_age = datetime.now().year - building.built_year

    return render_template(
        "building/building_detail.html",
        building=building,
        building_age=building_age
    )


# 建物編集

# 建物編集
@building_bp.route("/edit/<int:building_id>", methods=["GET", "POST"])
@login_required
def edit(building_id):

    # 編集対象の建物を取得
    building = Building.query.filter_by(
        building_id=building_id,
        user_id=current_user.user_id
    ).first_or_404()

    if request.method == "POST":

        # 入力された情報を取得
        building.building_name = request.form["building-name"]
        building.building_type_code = int(request.form["building-type"])

        age = int(request.form["building-age"])
        building.built_year = datetime.now().year - age

        building.prefecture = request.form["prefecture"]
        building.city = request.form["city"]

        # DBを更新
        db.session.commit()

        return redirect(
    url_for(
        "building.edit_complete",
        building_id=building.building_id
    )
)

    # 現在の築年数を計算
    building_age = datetime.now().year - building.built_year

    return render_template(
        "building/building_edit.html",
        building=building,
        building_age=building_age
    )



# 建物編集完了
@building_bp.route("/edit/complete/<int:building_id>")
@login_required
def edit_complete(building_id):

    building = Building.query.filter_by(
        building_id=building_id,
        user_id=current_user.user_id
    ).first_or_404()

    return render_template(
        "building/building_edit_complete.html",
        building=building
    )

# 建物削除確認
@building_bp.route("/delete/confirm/<int:building_id>")
@login_required
def delete_confirm(building_id):

    # ログイン中のユーザーが登録した建物だけ取得（他人の建物は404）
    building = Building.query.filter_by(
        building_id=building_id,
        user_id=current_user.user_id
    ).first_or_404()

    # 築年数を計算（detail / edit と同じ名前）
    building_age = datetime.now().year - building.built_year

    return render_template(
    "building/building_delete_confilm.html",
    building=building,
    building_age=building_age
    )


# 建物削除実行
@building_bp.route("/delete/<int:building_id>", methods=["POST"])
@login_required
def delete(building_id):

    building = Building.query.filter_by(
        building_id=building_id,
        user_id=current_user.user_id
    ).first_or_404()

    name = building.building_name

    try:
        db.session.delete(building)
        db.session.commit()
    except IntegrityError:
        # 分析結果などが紐づいていて消せない場合
        db.session.rollback()
        flash("この建物は分析履歴があるため削除できません。", "error")
        return redirect(url_for("building.edit", building_id=building_id))

    # 完了画面で名前を出すため、一時的に保存
    session["deleted_building_name"] = name
    return redirect(url_for("building.delete_complete"))


# 建物削除完了
@building_bp.route("/delete/complete")
@login_required
def delete_complete():
    name = session.pop("deleted_building_name", None)
    return render_template(
        "building/building_delete_complete.html",
        building_name=name
    )