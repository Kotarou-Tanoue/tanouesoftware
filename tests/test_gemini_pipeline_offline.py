"""API、Flask、MySQLを使わず写真→分析サービス→結果形式を確認するテスト。"""
from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "app" / "analysis" / "damage_analysis_service.py"
spec = importlib.util.spec_from_file_location("damage_analysis_offline_test", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakePhotoStorage:
    def __init__(self, photos):
        self.photos = photos
        self.read_keys = []

    def read_photo(self, key):
        self.read_keys.append(key)
        return self.photos[key]


class FakeGemini:
    is_mock = False
    requires_image_bytes = True

    def __init__(self):
        self.last_data = None

    def judgement_data(self, data, answers):
        self.last_data = data
        return False

    def generate_analysis_result(self, data, answers):
        self.last_data = data
        return {
            "is_mock": False,
            "damage_level": 2,
            "repair_cost_min": None,
            "repair_cost_max": None,
            "description": "【参考情報】専門家に点検を依頼してください。",
            "damage_locations": [],
            "repair_items": [],
            "photos": [{"s3_object_key": data["photos"][0]["s3_object_key"]}],
        }


class GeminiPipelineOfflineTests(unittest.TestCase):
    def setUp(self):
        output = BytesIO()
        Image.new("RGB", (100, 80), (225, 75, 75)).save(output, format="PNG")
        self.key = "photos/guest/a.png"
        self.photos = FakePhotoStorage({self.key: output.getvalue()})
        self.gemini = FakeGemini()
        self.service = mod.DamageAnalysisService(self.gemini)
        self.data = {
            "building": {"prefecture": "テスト県"},
            "report": {"door_window_status": 1},
            "locations": [{"location_name": "壁", "photos": [{"s3_object_key": self.key}]}],
            "photos": [{"s3_object_key": self.key}],
        }
        self.fake_flask = types.ModuleType("flask")
        self.fake_flask.current_app = types.SimpleNamespace(extensions={"photo_storage_service": self.photos})

    def test_01_pipeline_reads_photo_and_converts_to_jpeg(self):
        with patch.dict(sys.modules, {"flask": self.fake_flask}):
            response = self.service.analyze_damage(
                report_id=None, guest_analysis=self.data, user_id=None, answers=[]
            )
        self.assertEqual(response["status"], "completed")
        self.assertEqual(self.photos.read_keys, [self.key])
        self.assertEqual(response["result"]["damage_level"], 2)
        self.assertTrue(self.gemini.last_data["_gemini_image_jpegs"][0].startswith(b"\xff\xd8\xff"))
        self.assertNotIn("_gemini_image_jpegs", self.data)

    def test_02_duplicate_keys_are_read_once(self):
        self.data["photos"].append({"s3_object_key": self.key})
        with patch.dict(sys.modules, {"flask": self.fake_flask}):
            self.service.analyze_damage(
                report_id=None, guest_analysis=self.data, user_id=None, answers=[]
            )
        self.assertEqual(self.photos.read_keys, [self.key])

    def test_03_missing_image_fails_closed(self):
        self.photos.photos.clear()
        with patch.dict(sys.modules, {"flask": self.fake_flask}):
            with self.assertRaises(mod.AnalysisInputError):
                self.service.analyze_damage(
                    report_id=None, guest_analysis=self.data, user_id=None, answers=[]
                )

    def test_04_more_than_20_images_rejected(self):
        self.data["photos"] = [{"s3_object_key": f"photos/guest/{i}.jpg"} for i in range(21)]
        with patch.dict(sys.modules, {"flask": self.fake_flask}):
            with self.assertRaisesRegex(mod.AnalysisInputError, "20枚"):
                self.service.analyze_damage(
                    report_id=None, guest_analysis=self.data, user_id=None, answers=[]
                )

    def test_05_mock_keeps_original_path_without_photo_storage(self):
        class FakeMock(FakeGemini):
            is_mock = True
            requires_image_bytes = False
        service = mod.DamageAnalysisService(FakeMock())
        # Mock test still succeeds even without a registered photo service.
        response = service.analyze_damage(
            report_id=None, guest_analysis=self.data, user_id=None, answers=[]
        )
        self.assertEqual(response["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
