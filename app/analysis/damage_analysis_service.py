"""AI分析サービスの接続基盤（Gemini/API未実装でも単体試験可能）。

担当: 入力の取得/検証、追加質問の管理用正規化、AIクライアントの呼び出し、
分析結果の形式検証、ログイン利用者への結果保存委譲、画像の前処理。

DBは既存のSQLAlchemy Modelを使用し、S3写真取得はPhotoStorageService実装後に接続する。
本モジュール自体では被害判定や修理金額の算出を行わない。
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from typing import Any, Callable, Mapping, Protocol, Sequence


MAX_ANSWERS = 5
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_RESULT_BYTES = 128 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_EDGE = 1600


class AnalysisInputError(ValueError):
    """入力情報が不足、または形式が正しくない。"""


class AnalysisConfigurationError(RuntimeError):
    """未接続の外部機能（DB/S3/AI）が必要。"""


class GeminiAnalysisProtocol(Protocol):
    """今後実装するGeminiServiceの呼び出し契約。"""

    def judgement_data(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> bool:
        """追加質問が必要ならTrueを返す。"""

    def generate_followup_questions(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> str:
        """次の質問文を1件返す。"""

    def generate_analysis_result(
        self, analysis_data: Mapping[str, Any], answers: Sequence[dict[str, str]]
    ) -> Mapping[str, Any]:
        """結果を辞書で返す。"""


# データを取得する際、必ず権限を確認できる所有者IDを返すこと。
# 返す例: {"owner_user_id": 123, "building": {...}, "report": {...},
#          "locations": [...], "photos": [{"s3_object_key": "..."}]}
ReportLoader = Callable[[int, int | str], Mapping[str, Any] | None]
# DB側で analysis_history 保存とトランザクションの管理を実装する。
ResultSaver = Callable[[int, Mapping[str, Any], int | str], int | None]


class DamageAnalysisService:
    def __init__(
        self,
        gemini_service: GeminiAnalysisProtocol,
        *,
        report_loader: ReportLoader | None = None,
        result_saver: ResultSaver | None = None,
    ) -> None:
        self._gemini = gemini_service
        self._report_loader = report_loader
        self._result_saver = result_saver

    def analyze_damage(
        self,
        *,
        report_id: int | None,
        guest_analysis: dict[str, Any] | None,
        answers: list[dict[str, str]],
        user_id: int | str | None,
    ) -> dict[str, Any]:
        """設計書の分析処理。入力取得 → 追加情報判定 → 追加質問または結果生成。"""
        payload = self._load_input(
            report_id=report_id, guest_analysis=guest_analysis, user_id=user_id
        )
        normalized_answers = self.process_answers(answers)
        # 写真はS3オブジェクトキーで管理する。実画像の取得・前処理は
        # PhotoStorageService の実装後に preprocess_images() へ接続する。
        need_followup = self._gemini.judgement_data(payload, normalized_answers)
        if type(need_followup) is not bool:
            raise ValueError("AIの情報不足判定はboolである必要があります。")

        if need_followup:
            if len(normalized_answers) >= MAX_ANSWERS:
                raise AnalysisInputError("追加質問の上限回数に達しました。")
            question = self._gemini.generate_followup_questions(
                payload, normalized_answers
            )
            if not isinstance(question, str) or not question.strip():
                raise ValueError("追加質問の文章が取得できませんでした。")
            return {"status": "needs_followup", "question": question.strip()[:1000]}

        result = self._gemini.generate_analysis_result(payload, normalized_answers)
        validated = self._validate_result(result)
        return {"status": "completed", "result": validated}

    @staticmethod
    def process_answers(answers: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
        """未入力・巨大テキスト・想定外の型を拒否する。"""
        if not isinstance(answers, (list, tuple)) or len(answers) > MAX_ANSWERS:
            raise AnalysisInputError("追加回答の形式または件数が正しくありません。")
        clean: list[dict[str, str]] = []
        for item in answers:
            if not isinstance(item, Mapping):
                raise AnalysisInputError("追加回答は辞書形式で指定してください。")
            q, a = item.get("question"), item.get("answer")
            if not isinstance(q, str) or not isinstance(a, str):
                raise AnalysisInputError("質問と回答は文字列で指定してください。")
            q, a = q.strip(), a.strip()
            if not q or not a or len(q) > 1000 or len(a) > 2000:
                raise AnalysisInputError("質問または回答が空、または長すぎます。")
            clean.append({"question": q, "answer": a})
        return clean

    def save_analysis_result(
        self,
        *,
        report_id: int,
        result: dict[str, Any],
        user_id: int | str,
    ) -> int | None:
        """ログイン利用者の分析履歴と、AIが判定した被害箇所情報を保存する。

        ダミー分析結果はDBに保存しない。保存時は必ず所有者確認をやり直す。
        """
        if type(report_id) is not int or report_id <= 0:
            raise AnalysisInputError("report_idが不正です。")
        if user_id is None or isinstance(user_id, bool):
            raise AnalysisInputError("認証済みのuser_idが必要です。")
        validated = self._validate_result(result)
        if validated.get("is_mock") is True:
            raise AnalysisInputError("ダミーの分析結果をDBへ保存できません。")
        self._load_input(report_id=report_id, guest_analysis=None, user_id=user_id)

        if self._result_saver is not None:
            return self._result_saver(report_id, validated, user_id)

        # 設計書にある既存のAnalysisHistory/DamageLocation Modelを使用。
        from app.extensions import db
        from app.models import AnalysisHistory, DamageReport

        report = db.session.get(DamageReport, report_id)
        if report is None or report.building is None:
            raise AnalysisInputError("分析対象が存在しません。")
        if str(report.building.user_id) != str(user_id):
            raise PermissionError("この被害情報にはアクセスできません。")

        # 対象reportに属する箇所のみ更新できるよう事前に検証する。
        locations_by_id = {item.location_id: item for item in report.damage_locations}
        updates = []
        for item in validated.get("damage_locations", []):
            if not isinstance(item, Mapping) or "location_id" not in item:
                continue  # 表示用文字列・名称だけの項目はDB更新しない。
            location = locations_by_id.get(item["location_id"])
            if location is None:
                raise AnalysisInputError("他の被害状況に属する被害箇所は更新できません。")
            updates.append((location, item))

        history = AnalysisHistory(
            report_id=report_id,
            damage_level=validated["damage_level"],
            repair_cost_min=validated.get("repair_cost_min"),
            repair_cost_max=validated.get("repair_cost_max"),
            description=validated["description"],
        )
        try:
            db.session.add(history)
            for location, item in updates:
                if "description" in item:
                    location.description = item["description"]
                if "severity" in item:
                    location.severity = item["severity"]
            db.session.flush()
            analysis_id = history.analysis_id
            db.session.commit()
            return analysis_id
        except Exception:
            db.session.rollback()
            raise

    def _load_input(
        self,
        *,
        report_id: int | None,
        guest_analysis: dict[str, Any] | None,
        user_id: int | str | None,
    ) -> dict[str, Any]:
        if report_id is not None:
            if isinstance(report_id, bool) or not isinstance(report_id, int) or report_id <= 0:
                raise AnalysisInputError("report_idは正の整数にしてください。")
            if user_id is None or isinstance(user_id, bool):
                raise AnalysisInputError("ログイン利用者のIDがありません。")
            if guest_analysis is not None:
                raise AnalysisInputError("ログイン用・ゲスト用の入力を同時に渡せません。")
            if self._report_loader is not None:
                source = self._report_loader(report_id, user_id)
            else:
                # 追加クラス/ファイルを作らず、既存Modelから取得する。
                from app.extensions import db
                from app.models import DamageReport

                report = db.session.get(DamageReport, report_id)
                if report is None or report.building is None:
                    raise AnalysisInputError("分析対象が存在しません。")
                building = report.building
                source = {
                    "owner_user_id": building.user_id,
                    "building": {
                        "building_id": building.building_id,
                        "building_name": building.building_name,
                        "prefecture": building.prefecture,
                        "city": building.city,
                        "built_year": building.built_year,
                        "building_type_code": building.building_type_code,
                    },
                    "report": {
                        "report_id": report.report_id,
                        "door_window_status": report.door_window_status,
                        "noise_status": report.noise_status,
                        "tilt_status": report.tilt_status,
                    },
                    "locations": [],
                    "photos": [],
                }
                for location in report.damage_locations:
                    item = {
                        "location_id": location.location_id,
                        "location_name": location.location_name,
                        "location_type": location.location_type,
                        "damage_type": location.damage_type,
                        "earthquake_relation": location.earthquake_relation,
                        "description": location.description,
                        "severity": location.severity,
                        "photos": [],
                    }
                    for photo in location.damage_photos:
                        photo_data = {
                            "photo_id": photo.photo_id,
                            "location_id": location.location_id,
                            "s3_object_key": photo.s3_object_key,
                        }
                        item["photos"].append(photo_data)
                        source["photos"].append(photo_data)
                    source["locations"].append(item)
            if not isinstance(source, Mapping):
                raise AnalysisInputError("分析対象が存在しません。")
            owner_id = source.get("owner_user_id")
            if owner_id is None or str(owner_id) != str(user_id):
                raise PermissionError("この被害情報にはアクセスできません。")
        else:
            if user_id is not None:
                raise AnalysisInputError("ログイン利用者のreport_idがありません。")
            source = guest_analysis
            if not isinstance(source, dict) or not source:
                raise AnalysisInputError("分析対象の入力情報がありません。")

        try:
            payload = deepcopy(dict(source))
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AnalysisInputError("分析対象はJSONで扱える形式にしてください。") from exc
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise AnalysisInputError("入力情報のサイズが上限を超えています。")
        return payload

    @staticmethod
    def _validate_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise ValueError("AI分析結果は辞書形式で指定してください。")
        data = dict(result)
        level = data.get("damage_level")
        if type(level) is not int or not 1 <= level <= 5:
            raise ValueError("damage_levelは1から5の整数です。")
        lo, hi = data.get("repair_cost_min"), data.get("repair_cost_max")
        if any(x is not None and (type(x) is not int or x < 0) for x in (lo, hi)):
            raise ValueError("修理費用は0以上の整数またはnullです。")
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("修理費用の上下限が逆転しています。")
        if not isinstance(data.get("description"), str) or not data["description"].strip():
            raise ValueError("分析結果の説明文がありません。")
        for field in ("damage_locations", "repair_items", "photos"):
            if field in data and not isinstance(data[field], list):
                raise ValueError(f"{field} はリスト形式にしてください。")
        for location in data.get("damage_locations", []):
            if not isinstance(location, Mapping):
                if isinstance(location, str):  # 結果画面の表示用
                    continue
                raise ValueError("被害箇所は辞書または文字列で指定してください。")
            if "location_id" in location:
                loc_id = location["location_id"]
                if type(loc_id) is not int or loc_id <= 0:
                    raise ValueError("location_id は正の整数です。")
            if "severity" in location:
                severity = location["severity"]
                if type(severity) is not int or not 0 <= severity <= 4:
                    raise ValueError("severity は0から4の整数です。")
            if "description" in location:
                if not isinstance(location["description"], str):
                    raise ValueError("被害箇所の説明は文字列で指定してください。")
        try:
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("分析結果がJSON形式に変換できません。") from exc
        if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("分析結果のサイズが上限を超えています。")
        return data

    @staticmethod
    def preprocess_images(image_data: bytes) -> bytes:
        """写真を扱いやすいJPEGに正規化する。S3からの取得自体は別サービスが行う。

        EXIFの向き修正、縮小、RGB化を行い、ピクセル数とバイト数を制限する。
        画像からの被害認識は一切行わない。
        """
        if not isinstance(image_data, bytes) or not image_data:
            raise AnalysisInputError("写真データを指定してください。")
        if len(image_data) > MAX_IMAGE_BYTES:
            raise AnalysisInputError("写真データが10MBを超えています。")
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
            with Image.open(BytesIO(image_data)) as img:
                if img.format not in {"JPEG", "PNG", "WEBP"}:
                    raise AnalysisInputError("対応写真形式はJPEG、PNG、WEBPです。")
                if img.width * img.height > MAX_IMAGE_PIXELS:
                    raise AnalysisInputError("写真の解像度が大きすぎます。")
                img = ImageOps.exif_transpose(img)
                img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    rgba = img.convert("RGBA")
                    canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                    canvas.paste(rgba, mask=rgba.getchannel("A"))
                    img = canvas
                else:
                    img = img.convert("RGB")
                output = BytesIO()
                img.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue()
        except AnalysisInputError:
            raise
        except (OSError, ValueError) as exc:
            raise AnalysisInputError("写真データの読込・変換に失敗しました。") from exc
