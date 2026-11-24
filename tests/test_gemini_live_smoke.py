"""実Google Gemini APIを1回だけ呼ぶ手動スモークテスト（DBに書き込まない）。"""
from io import BytesIO
import os
from pathlib import Path
import sys

from PIL import Image, ImageDraw
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.analysis.damage_analysis_service import DamageAnalysisService
from app.analysis.gemini_service import GeminiService


def main():
    if os.environ.get("ANALYSIS_USE_GEMINI") != "1":
        raise RuntimeError(".env に ANALYSIS_USE_GEMINI=1 を設定してください。")
    service = GeminiService(use_mock=False)
    image = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 50, 150, 150), outline="red", width=8)
    buf = BytesIO()
    image.save(buf, format="PNG")
    jpeg = DamageAnalysisService.preprocess_images(buf.getvalue())
    data = {
        "building": {"prefecture": "検証用", "building_type_code": 1},
        "report": {"door_window_status": 0, "noise_status": 0, "tilt_status": 0},
        "locations": [],
        "photos": [],
        "_gemini_image_jpegs": [jpeg],
    }
    print("MODEL:", os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"), flush=True)
    print("LIVE IMAGE + JUDGEMENT REQUEST START...", flush=True)
    needs = service.judgement_data(data, [])
    assert type(needs) is bool
    print("GEMINI SERVICE IMAGE REQUEST: PASS")
    print("NEEDS_FOLLOWUP:", needs)
    print("NOTE: This only checks API connectivity / JSON handling. No damage decision or DB write.")


if __name__ == "__main__":
    main()
