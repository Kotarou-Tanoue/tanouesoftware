"""分析結果への質問サービス（クラス図 ChatService）。

ChatHistory は設計済みの既存 Model を使用する。
ゲスト、未保存の分析、およびダミーAIの会話は DB に保存しない。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.extensions import db
from app.models import AnalysisHistory, ChatHistory

MAX_CHAT_QUESTION_LENGTH = 2000
MAX_CHAT_ANSWER_LENGTH = 10000


class ChatService:
    def __init__(self, gemini_service: Any):
        self._gemini = gemini_service

    @property
    def is_mock(self) -> bool:
        """開発用ダミー回答を本物のAI応答として永続化しない。"""
        return getattr(self._gemini, "is_mock", False) is True

    def process_chatbot(
        self,
        question: str,
        analysis_result: Mapping[str, Any],
        chat_history: Sequence[Mapping[str, str]] = (),
    ) -> str:
        """GeminiService に分析結果と過去の会話を渡して応答を取得。"""
        if not isinstance(question, str) or not (1 <= len(question.strip()) <= MAX_CHAT_QUESTION_LENGTH):
            raise ValueError("質問を1～2000文字で入力してください。")
        if not isinstance(analysis_result, Mapping) or not analysis_result:
            raise ValueError("参照する分析結果がありません。")
        answer = self._gemini.generate_chat_response(
            analysis_result, question.strip(), chat_history[-10:]
        )
        if not isinstance(answer, str) or not (1 <= len(answer.strip()) <= MAX_CHAT_ANSWER_LENGTH):
            raise ValueError("AIから有効な回答を取得できませんでした。")
        return answer.strip()

    @staticmethod
    def _owned_analysis(analysis_id: int, user_id: int) -> AnalysisHistory:
        """DBから取得する場合は必ず建物の所有者を照合する。"""
        if type(analysis_id) is not int or analysis_id <= 0 or type(user_id) is not int:
            raise PermissionError("分析履歴へのアクセス権がありません。")
        analysis = db.session.get(AnalysisHistory, analysis_id)
        if (analysis is None or analysis.damage_report is None
                or analysis.damage_report.building is None
                or analysis.damage_report.building.user_id != user_id):
            raise PermissionError("分析履歴へのアクセス権がありません。")
        return analysis

    def get_chat_history(self, analysis_id: int, user_id: int) -> list[dict[str, str]]:
        """設計済み ChatHistory から指定した分析の会話を取得する。"""
        self._owned_analysis(analysis_id, user_id)
        rows = db.session.execute(
            db.select(ChatHistory)
            .where(ChatHistory.analysis_id == analysis_id)
            .order_by(ChatHistory.created_at.asc(), ChatHistory.chat_id.asc())
        ).scalars().all()
        return [
            {"question": row.user_question, "answer": row.ai_answer}
            for row in rows
        ]

    def save_message(self, analysis_id: int, user_id: int, question: str, answer: str) -> int | None:
        """ログイン済みの本人の正式な分析履歴にのみ保存。"""
        if self.is_mock:
            return None
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
            raise ValueError("質問または回答が空です。")
        self._owned_analysis(analysis_id, user_id)
        try:
            row = ChatHistory(
                analysis_id=analysis_id,
                user_question=question.strip(),
                ai_answer=answer.strip(),
            )
            db.session.add(row)
            db.session.commit()
            return row.chat_id
        except Exception:
            db.session.rollback()
            raise
