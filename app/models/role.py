"""権限テーブルのModel。"""

from app.extensions import db


class Role(db.Model):
    __tablename__ = "role"

    role_code = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="権限コード",
    )
    role_name = db.Column(db.String(10), nullable=False, comment="権限名")

    users = db.relationship("User", back_populates="role")
