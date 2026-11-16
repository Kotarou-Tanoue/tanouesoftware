"""認証方式テーブルのModel。"""

from app.extensions import db


class Provider(db.Model):
    __tablename__ = "provider"

    provider_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="認証方式コード",
    )
    provider_name = db.Column(db.String(30), nullable=False, comment="認証方式名")

    authentications = db.relationship("UserAuth", back_populates="provider")
