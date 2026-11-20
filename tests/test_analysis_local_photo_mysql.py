"""Result-page local photo display / ownership integration test (tanouesoftware v9).

Run from project root:
    .\\.venv\\Scripts\\python.exe .\\tests\\test_analysis_local_photo_mysql.py

Local development MySQL ONLY. Creates two temporary DamagePhoto records and
three temporary files under instance/uploads. Only these are deleted afterward.
AI / LINE OAuth / S3 are not called.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from urllib.parse import quote

from PIL import Image
from sqlalchemy import func, select, text
from werkzeug.datastructures import FileStorage

from app import create_app
from app.analysis_input.local_photo_storage import LocalPhotoStorage
from app.common.photos import get_photo_keys_for_report
from app.extensions import db
from app.models.damage_location import DamageLocation
from app.models.damage_photo import DamagePhoto
from app.models.damage_report import DamageReport
from app.models.user import User

app = create_app()
app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

OWNER_ID = 2
OTHER_ID = 3
REPORT_ID = 1
RESULT_SENTINEL = "LOCAL_PHOTO_TEST_RESULT"
RESULT = {
    "damage_level": 2,
    "repair_cost_min": 10000,
    "repair_cost_max": 20000,
    "description": RESULT_SENTINEL,
    "damage_locations": [],
    "repair_items": [],
    "photos": [],
    "is_mock": True,
}


def passed(label: str, detail: str = "") -> None:
    print(f"{label}: PASS" + (f" ({detail})" if detail else ""))


def login_dev(client, user_id: int) -> None:
    page = client.get("/auth/login/dev")
    assert page.status_code == 200, f"Login page HTTP {page.status_code}"
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        page.get_data(as_text=True),
    )
    assert match, "Login CSRF token not found"
    response = client.post(
        "/auth/login/dev",
        data={"user_id": str(user_id), "csrf_token": match.group(1)},
        follow_redirects=False,
    )
    assert response.status_code == 302, f"Login POST HTTP {response.status_code}"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(user_id)


def image_bytes(fmt: str, color: tuple[int, int, int]) -> bytes:
    buf = BytesIO()
    with Image.new("RGB", (28, 20), color) as img:
        img.save(buf, format=fmt)
    return buf.getvalue()


def upload(storage: LocalPhotoStorage, data: bytes, filename: str, *, user_id=None):
    photo = FileStorage(stream=BytesIO(data), filename=filename)
    try:
        return storage.upload_photo(photo, user_id=user_id)
    finally:
        photo.close()


def photo_url(key: str) -> str:
    return "/photo-files/" + quote(key, safe="/")


def assert_photo(client, key: str, data: bytes, mimetype: str) -> None:
    response = client.get(photo_url(key))
    assert response.status_code == 200, f"Photo HTTP {response.status_code}"
    assert response.mimetype == mimetype, response.mimetype
    assert response.data == data, "Photo bytes mismatch"
    assert "private" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def seed_result_session(client, report_id, user_id, guest=None) -> None:
    with client.session_transaction() as sess:
        if report_id is None:
            sess.pop("report_id", None)
            sess["guest_analysis"] = guest
        else:
            sess["report_id"] = report_id
            sess.pop("guest_analysis", None)
        sess["analysis_result"] = dict(RESULT)
        sess["analysis_result_context"] = {
            "report_id": report_id,
            "user_id": user_id,
        }


print("=== ANALYSIS LOCAL PHOTO / MYSQL INTEGRATION TEST ===")

# App context is used ONLY around direct DB work, never across Flask client
# requests: this prevents Flask-Login's request user from leaking between tests.
with app.app_context():
    database = db.session.execute(text("SELECT DATABASE()")).scalar()
    host = db.engine.url.host
    assert db.engine.dialect.name == "mysql", "MySQL is required"
    assert host in {"localhost", "127.0.0.1", "::1"}, "Refusing nonlocal MySQL"
    assert database == "tanouesoftware_db", f"Wrong database: {database}"
    storage = app.extensions.get("photo_storage_service")
    assert isinstance(storage, LocalPhotoStorage), "LocalPhotoStorage is required"
    assert storage.base_dir == (Path(app.instance_path) / "uploads").resolve()

    report = db.session.get(DamageReport, REPORT_ID)
    assert report is not None and report.building.user_id == OWNER_ID
    assert db.session.get(User, OWNER_ID) and db.session.get(User, OTHER_ID)
    location = db.session.scalars(
        select(DamageLocation)
        .where(DamageLocation.report_id == REPORT_ID)
        .order_by(DamageLocation.location_id)
    ).first()
    assert location is not None, "No damage location for report_id=1"
    location_id = location.location_id
    before_photo_count = db.session.scalar(select(func.count()).select_from(DamagePhoto))
    passed("DATABASE CHECK", f"{database} @ {host}; owner=2; report=1")

created_keys: list[str] = []
registered_keys: list[str] = []
completed = False

try:
    owner_png = image_bytes("PNG", (32, 100, 180))
    owner_jpg = image_bytes("JPEG", (210, 140, 70))
    guest_png = image_bytes("PNG", (80, 210, 90))

    owner_key1 = upload(storage, owner_png, "test-owner-1.png", user_id=OWNER_ID)
    created_keys.append(owner_key1)
    owner_key2 = upload(storage, owner_jpg, "test-owner-2.jpg", user_id=OWNER_ID)
    created_keys.append(owner_key2)
    guest_key = upload(storage, guest_png, "test-guest.png", user_id=None)
    created_keys.append(guest_key)
    passed("TEST 1 TEMPORARY FILES CREATED", "owner 2 photos; guest 1 photo")

    with app.app_context():
        for key in (owner_key1, owner_key2):
            db.session.add(DamagePhoto(location_id=location_id, s3_object_key=key))
        db.session.commit()
        registered_keys.extend((owner_key1, owner_key2))
        keys = get_photo_keys_for_report(REPORT_ID, OWNER_ID)
        assert owner_key1 in keys and owner_key2 in keys
        assert keys.index(owner_key1) < keys.index(owner_key2)
        other_keys = get_photo_keys_for_report(REPORT_ID, OTHER_ID)
        assert owner_key1 not in other_keys and owner_key2 not in other_keys
    passed("TEST 2 MYSQL KEYS / OWNERSHIP", "two temporary photo records")

    # Use independent browser clients for each identity.
    owner = app.test_client()
    login_dev(owner, OWNER_ID)
    seed_result_session(owner, REPORT_ID, OWNER_ID)
    response = owner.get("/analysis/result")
    assert response.status_code == 200, f"Result HTTP {response.status_code}"
    html = response.get_data(as_text=True)
    assert photo_url(owner_key1) in html, "Owner photo #1 not rendered"
    assert photo_url(owner_key2) in html, "Owner photo #2 not rendered"
    assert "写真1を保存する" in html and "写真2を保存する" in html
    passed("TEST 3 RESULT PAGE SHOWS MULTIPLE PHOTOS", "HTTP 200")

    assert_photo(owner, owner_key1, owner_png, "image/png")
    assert_photo(owner, owner_key2, owner_jpg, "image/jpeg")
    passed("TEST 4 OWNER CAN READ PHOTOS", "PNG/JPEG HTTP 200, bytes identical")

    other = app.test_client()
    login_dev(other, OTHER_ID)
    with other.session_transaction() as sess:
        sess["report_id"] = REPORT_ID  # knowing report_id is not authorization
    assert other.get(photo_url(owner_key1)).status_code == 404
    assert other.get(photo_url(owner_key2)).status_code == 404
    passed("TEST 5 NON-OWNER BLOCKED", "both HTTP 404")

    anonymous = app.test_client()
    assert anonymous.get(photo_url(owner_key1)).status_code == 404
    passed("TEST 6 ANONYMOUS OWNER-PHOTO BLOCKED", "HTTP 404")

    guest = app.test_client()
    seed_result_session(
        guest, None, None,
        guest={"photos": [{"s3_object_key": guest_key}]},
    )
    guest_page = guest.get("/analysis/result")
    assert guest_page.status_code == 200
    assert photo_url(guest_key) in guest_page.get_data(as_text=True)
    assert_photo(guest, guest_key, guest_png, "image/png")
    passed("TEST 7 GUEST OWN PHOTO", "result and image HTTP 200")

    unrelated_guest = app.test_client()
    assert unrelated_guest.get(photo_url(guest_key)).status_code == 404
    assert other.get(photo_url(guest_key)).status_code == 404
    assert guest.get(photo_url(owner_key1)).status_code == 404
    passed("TEST 8 DIFFERENT SESSION / OWNER BLOCKED", "HTTP 404")

    no_photos = app.test_client()
    seed_result_session(no_photos, None, None, guest={"photos": []})
    empty_page = no_photos.get("/analysis/result")
    assert empty_page.status_code == 200
    assert "表示可能な写真データはありません。" in empty_page.get_data(as_text=True)
    passed("TEST 9 EMPTY PHOTO DISPLAY", "HTTP 200")
    completed = True

finally:
    try:
        with app.app_context():
            db.session.rollback()
            if registered_keys:
                rows = db.session.scalars(
                    select(DamagePhoto).where(DamagePhoto.s3_object_key.in_(registered_keys))
                ).all()
                for row in rows:
                    db.session.delete(row)
                db.session.commit()
            db.session.remove()
    finally:
        for key in created_keys:
            storage.delete_photo(key)

    with app.app_context():
        after_photo_count = db.session.scalar(select(func.count()).select_from(DamagePhoto))
    print(f"DamagePhoto: {before_photo_count} -> {after_photo_count}")
    assert after_photo_count == before_photo_count, "Temporary MySQL rows remain"
    for key in created_keys:
        assert not storage._path_for(key).exists(), "Temporary photo file remains"
    passed("TEST 10 TEMP DATA CLEANUP", "MySQL rows and local files removed")

if completed:
    print("\n=== ALL 10 LOCAL PHOTO TESTS PASSED ===")
