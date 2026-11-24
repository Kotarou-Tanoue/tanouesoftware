"""Gemini API通信をMockTransportで代替する無課金・非DBのオフラインテスト。"""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "app" / "analysis" / "gemini_service.py"
spec = importlib.util.spec_from_file_location("gemini_service_test_under_test", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
GeminiService = mod.GeminiService


class GeminiServiceOfflineTests(unittest.TestCase):
    def setUp(self):
        self.api = GeminiService(use_mock=False, api_key="placeholder-test-key", model="gemini-3.5-flash-lite")
        self.calls = []

    def mock_http(self, handler):
        actual_client = httpx.Client
        def build_client(*args, **kwargs):
            return actual_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout", 60))
        return patch.object(mod.httpx, "Client", side_effect=build_client)

    @staticmethod
    def response(payload, status=200):
        return httpx.Response(status, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]})

    def test_01_default_mock_keeps_original_contract(self):
        service = GeminiService()
        self.assertTrue(service.is_mock)
        self.assertFalse(service.requires_image_bytes)
        self.assertTrue(service.judgement_data({}, []))
        self.assertFalse(service.judgement_data({}, [{"question": "a", "answer": "b"}]))
        self.assertEqual(service.generate_analysis_result({}, [])["is_mock"], True)

    def test_02_real_mode_requires_key(self):
        with patch.dict(mod.os.environ, {"GEMINI_API_KEY": ""}, clear=True):
            with self.assertRaises(RuntimeError):
                GeminiService(use_mock=False)

    def test_03_real_judgement_json_and_image(self):
        def handler(req):
            self.calls.append(req)
            data = json.loads(req.content)
            self.assertEqual(req.headers["x-goog-api-key"], "placeholder-test-key")
            self.assertEqual(data["generationConfig"]["responseMimeType"], "application/json")
            parts = data["contents"][0]["parts"]
            self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
            self.assertEqual(parts[1]["inline_data"]["data"], "/9j/")
            return self.response({"needs_followup": True})
        with self.mock_http(handler):
            result = self.api.judgement_data({"photos": [], "_gemini_image_jpegs": [b"\xff\xd8\xff"]}, [])
        self.assertTrue(result)
        self.assertEqual(len(self.calls), 1)

    def test_04_followup_question_real(self):
        with self.mock_http(lambda req: self.response({"question": "建物は傾いていますか？"})):
            self.assertEqual(self.api.generate_followup_questions({"building": {}}, []), "建物は傾いていますか？")

    def test_05_result_schema_and_photo_keys_preserved(self):
        source = {"photos": [{"s3_object_key": "photos/user_4/img.jpg"}], "locations": [{"location_id": 5, "location_name": "壁"}]}
        def handler(req):
            return self.response({"damage_level": 2, "description": "壁面に亀裂が見られます", "damage_locations": [{"location_id": 5, "location_name": "壁", "severity": 1}]})
        with self.mock_http(handler):
            result = self.api.generate_analysis_result(source, [])
        self.assertFalse(result["is_mock"])
        self.assertIsNone(result["repair_cost_min"])
        self.assertEqual(result["photos"], [{"s3_object_key": "photos/user_4/img.jpg"}])
        self.assertIn("参考情報", result["description"])

    def test_06_result_rejects_unowned_location_id(self):
        source = {"locations": [{"location_id": 5}], "photos": []}
        with self.mock_http(lambda req: self.response({"damage_level": 2, "description": "説明", "damage_locations": [{"location_id": 999, "location_name": "壁"}]})):
            with self.assertRaisesRegex(ValueError, "入力にない被害箇所"):
                self.api.generate_analysis_result(source, [])

    def test_07_chat_is_text_and_no_json_mode(self):
        def handler(req):
            self.assertNotIn("responseMimeType", json.loads(req.content)["generationConfig"])
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "専門家に現地確認を依頼してください。"}]}}]})
        with self.mock_http(handler):
            answer = self.api.generate_chat_response({"damage_level": 2}, "安全ですか？", [])
        self.assertIn("専門家", answer)

    def test_08_503_retries_once_then_fails(self):
        def handler(req):
            self.calls.append(req)
            return httpx.Response(503, json={"error": {"message": "unavailable"}})
        with self.mock_http(handler), patch.object(mod.time, "sleep", return_value=None):
            with self.assertRaises(TimeoutError):
                self.api.judgement_data({}, [])
        self.assertEqual(len(self.calls), 2)

    def test_09_malformed_json_is_rejected(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not JSON"}]}}]})):
            with self.assertRaisesRegex(ValueError, "JSON形式"):
                self.api.judgement_data({}, [])

    def test_10_maximum_answers_stop_followup(self):
        answers = [{"question": "Q", "answer": "A"}] * 5
        self.assertFalse(self.api.judgement_data({}, answers))

    def test_11_private_ids_and_photo_keys_not_sent_to_model(self):
        payload = self.api._public_data({
            "owner_user_id": 4,
            "building": {"building_id": 7, "building_name": "private name", "prefecture": "熊本県"},
            "report": {"report_id": 99, "noise_status": 1},
            "locations": [{"location_id": 8, "photos": [{"s3_object_key": "secret-key"}]}],
            "photos": [{"s3_object_key": "secret-key"}],
            "_gemini_image_jpegs": [b"fake"],
        })
        data = json.dumps(payload, ensure_ascii=False)
        for text in ("private name", "secret-key", "owner_user_id", "report_id", "building_id"):
            self.assertNotIn(text, data)
        self.assertEqual(payload["photo_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
