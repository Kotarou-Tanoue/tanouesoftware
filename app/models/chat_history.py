"""チャット履歴テーブルのModel。"""

from app.extensions import db


class ChatHistory(db.Model):
    __tablename__ = "chat_history"

    chat_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="チャット履歴ID",
    )
    analysis_id = db.Column(
        db.Integer,
        db.ForeignKey("analysis_history.analysis_id"),
        nullable=False,
        comment="分析履歴ID",
    )
    user_question = db.Column(db.Text, nullable=False, comment="利用者の質問")
    ai_answer = db.Column(db.Text, nullable=False, comment="AIの回答")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )

    analysis_history = db.relationship(
        "AnalysisHistory", back_populates="chat_histories"
    )
