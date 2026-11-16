"""建物種別テーブルのModel。"""

from app.extensions import db


class BuildingType(db.Model):
    __tablename__ = "building_type"

    type_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="建物種別コード",
    )
    type_name = db.Column(db.String(10), nullable=False, comment="建物種別名")

    buildings = db.relationship("Building", back_populates="building_type")
