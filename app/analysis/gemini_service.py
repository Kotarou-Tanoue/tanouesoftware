"""開発・画面遷移テスト用のGeminiServiceダミー実装。実際の被害判定には使用しない。"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


class GeminiService:
    """初回は追加質問、回答後は明確にダミーと記した結果を返す。"""

    def judgement_data(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> bool:
        return not answers

    def generate_followup_questions(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> str:
        return "【開発用の追加質問】建物の被害について補足情報を入力してください。"

    def generate_analysis_result(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> Mapping[str, Any]:
        return {
            "is_mock": True,
            "damage_level": 1,  # 画面遷移確認用の仮値。実際の被害レベルではない。
            "repair_cost_min": None,
            "repair_cost_max": None,
            "description": (
                "【動作確認用のダミー結果です】実際のAI分析や建物の安全性判定は"
                "行っていません。被害レベル1は画面表示テスト用の仮値です。"
            ),
            "damage_locations": [],
            "repair_items": [],
            "photos": [],
        }
