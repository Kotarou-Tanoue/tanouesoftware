"""地震関連性テーブルのModel。"""

from app.extensions import db


class EarthquakeRelation(db.Model):
    __tablename__ = "earthquake_relation"

    relation_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="地震関連性コード",
    )
    relation = db.Column(db.String(5), nullable=False, comment="地震関連性")

    damage_locations = db.relationship(
        "DamageLocation", back_populates="earthquake_relation_master"
    )
