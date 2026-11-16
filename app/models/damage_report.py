"""被害状況テーブルのModel。"""

from app.extensions import db


class DamageReport(db.Model):
    __tablename__ = "damage_report"

    report_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="被害状況ID",
    )
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("building.building_id"),
        nullable=False,
        comment="建物ID",
    )
    door_window_status = db.Column(
        db.Integer,
        db.ForeignKey("damage_status.status_code"),
        nullable=False,
        comment="ドア・窓の開閉状況",
    )
    noise_status = db.Column(
        db.Integer,
        db.ForeignKey("damage_status.status_code"),
        nullable=False,
        comment="異音の有無",
    )
    tilt_status = db.Column(
        db.Integer,
        db.ForeignKey("damage_status.status_code"),
        nullable=False,
        comment="建物の傾斜の有無",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )

    building = db.relationship("Building", back_populates="damage_reports")

    door_window_status_master = db.relationship(
        "DamageStatus",
        back_populates="door_window_reports",
        foreign_keys="DamageReport.door_window_status",
    )

    noise_status_master = db.relationship(
        "DamageStatus",
        back_populates="noise_reports",
        foreign_keys="DamageReport.noise_status",
    )

    tilt_status_master = db.relationship(
        "DamageStatus",
        back_populates="tilt_reports",
        foreign_keys="DamageReport.tilt_status",
    )

    damage_locations = db.relationship("DamageLocation", back_populates="damage_report")

    analysis_histories = db.relationship(
        "AnalysisHistory", back_populates="damage_report"
    )
