"""被害箇所テーブルのModel。"""

from app.extensions import db


class DamageLocation(db.Model):
    __tablename__ = "damage_location"

    location_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="被害箇所ID",
    )
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("damage_report.report_id"),
        nullable=False,
        comment="被害状況ID",
    )
    location_name = db.Column(db.String(50), nullable=False, comment="被害箇所名")
    location_type = db.Column(db.String(30), nullable=False, comment="被害箇所種別")
    damage_type = db.Column(db.String(30), nullable=False, comment="被害種別")
    earthquake_relation = db.Column(
        db.Integer,
        db.ForeignKey("earthquake_relation.relation_code"),
        nullable=False,
        comment="地震との関連",
    )
    description = db.Column(db.Text, nullable=True, comment="被害箇所詳細説明")
    severity = db.Column(
        db.Integer,
        db.ForeignKey("location_severity.severity_code"),
        nullable=True,
        comment="被害程度",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )

    damage_report = db.relationship("DamageReport", back_populates="damage_locations")

    earthquake_relation_master = db.relationship(
        "EarthquakeRelation", back_populates="damage_locations"
    )

    severity_master = db.relationship(
        "LocationSeverity", back_populates="damage_locations"
    )

    damage_photos = db.relationship("DamagePhoto", back_populates="damage_location")
