"""被害箇所毎被害程度テーブルのModel。"""

from app.extensions import db


class LocationSeverity(db.Model):
    __tablename__ = "location_severity"

    severity_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="被害程度コード",
    )
    severity = db.Column(db.String(5), nullable=False, comment="被害程度")

    damage_locations = db.relationship(
        "DamageLocation", back_populates="severity_master"
    )
