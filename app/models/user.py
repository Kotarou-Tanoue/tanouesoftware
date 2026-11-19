"""利用者テーブルのModel。"""

from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"

    user_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="利用者ID",
    )
    role_code = db.Column(
        db.Integer,
        db.ForeignKey("role.role_code"),
        nullable=False,
        default=1,
        server_default=db.text("1"),
        comment="権限コード",
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

    role = db.relationship("Role", back_populates="users")

    authentications = db.relationship("UserAuth", back_populates="user")

    buildings = db.relationship("Building", back_populates="user")

    def get_id(self):
        return str(self.user_id)
