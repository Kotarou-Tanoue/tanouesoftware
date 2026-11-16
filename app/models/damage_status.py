"""被害状況ステータステーブルのModel。"""

from app.extensions import db


class DamageStatus(db.Model):
    __tablename__ = "damage_status"

    status_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="被害状況ステータスコード",
    )
    status_name = db.Column(
        db.String(5), nullable=False, comment="被害状況ステータス名"
    )

    door_window_reports = db.relationship(
        "DamageReport",
        back_populates="door_window_status_master",
        foreign_keys="DamageReport.door_window_status",
    )

    noise_reports = db.relationship(
        "DamageReport",
        back_populates="noise_status_master",
        foreign_keys="DamageReport.noise_status",
    )

    tilt_reports = db.relationship(
        "DamageReport",
        back_populates="tilt_status_master",
        foreign_keys="DamageReport.tilt_status",
    )
