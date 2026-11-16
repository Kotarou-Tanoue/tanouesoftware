"""被害写真テーブルのModel。"""

from app.extensions import db


class DamagePhoto(db.Model):
    __tablename__ = "damage_photo"

    photo_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="被害写真ID",
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey("damage_location.location_id"),
        nullable=False,
        comment="被害箇所ID",
    )
    s3_object_key = db.Column(
        db.String(1024), nullable=False, comment="S3のオブジェクトキー"
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )

    damage_location = db.relationship("DamageLocation", back_populates="damage_photos")
