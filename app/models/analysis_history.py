"""分析履歴テーブルのModel。"""

from app.extensions import db


class AnalysisHistory(db.Model):
    __tablename__ = "analysis_history"

    analysis_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="分析履歴ID",
    )
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("damage_report.report_id"),
        nullable=False,
        comment="被害状況ID",
    )
    damage_level = db.Column(db.Integer, nullable=False, comment="被害レベル")
    repair_cost_min = db.Column(db.Integer, nullable=True, comment="修理費用推定下限")
    repair_cost_max = db.Column(db.Integer, nullable=True, comment="修理費用推定上限")
    description = db.Column(db.Text, nullable=True, comment="分析詳細")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
        comment="作成日時",
    )

    damage_report = db.relationship("DamageReport", back_populates="analysis_histories")

    chat_histories = db.relationship("ChatHistory", back_populates="analysis_history")

    __table_args__ = (
        db.CheckConstraint(
            "damage_level BETWEEN 1 AND 5", name="ck_analysis_history_damage_level"
        ),
    )
