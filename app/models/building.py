"""建物テーブルのModel。"""

from app.extensions import db


class Building(db.Model):
    __tablename__ = "building"

    building_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="建物ID",
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.user_id"), nullable=False, comment="利用者ID"
    )
    building_name = db.Column(db.String(100), nullable=False, comment="建物名")
    prefecture = db.Column(db.String(10), nullable=False, comment="都道府県")
    city = db.Column(db.String(100), nullable=False, comment="市区町村")
    built_year = db.Column(db.Integer, nullable=False, comment="建築年")
    building_type_code = db.Column(
        db.Integer,
        db.ForeignKey("building_type.type_code"),
        nullable=False,
        comment="建物種別コード",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=db.FetchedValue(),
        comment="更新日時",
    )

    user = db.relationship("User", back_populates="buildings")

    building_type = db.relationship("BuildingType", back_populates="buildings")

    damage_reports = db.relationship("DamageReport", back_populates="building")
