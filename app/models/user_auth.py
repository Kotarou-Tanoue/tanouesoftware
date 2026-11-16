"""利用者認証テーブルのModel。"""

from app.extensions import db


class UserAuth(db.Model):
    __tablename__ = "user_auth"

    provider_code = db.Column(
        db.Integer,
        db.ForeignKey("provider.provider_code"),
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="認証方式コード",
    )
    provider_user_id = db.Column(
        db.String(255),
        primary_key=True,
        autoincrement=False,
        nullable=False,
        comment="認証先ユーザーID",
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.user_id"), nullable=False, comment="利用者ID"
    )
    password_hash = db.Column(
        db.String(255), nullable=True, comment="パスワードハッシュ"
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

    user = db.relationship("User", back_populates="authentications")

    provider = db.relationship("Provider", back_populates="authentications")

    __table_args__ = (
        db.CheckConstraint(
            "provider_code <> 0 OR (password_hash IS NOT NULL AND password_hash <> '')",
            name="ck_user_auth_email_password_hash",
        ),
    )
