r"""Read-only LINE-linked user security integration checks for tanouesoftware(8).

Run from the project root after copying this file into tests/:
    .\.venv\Scripts\python.exe .\tests\test_line_linked_analysis_security.py

This does not invoke the actual LINE OAuth callback. It simulates an already
validated Flask-Login session for a user with a LINE identity in MySQL.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import Mock

from flask import jsonify
from flask_login import current_user
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "app").is_dir() and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AnalysisHistory, Building, DamageReport, User, UserAuth  # noqa: E402
from app.analysis.chat_service import ChatService  # noqa: E402
from app.analysis.damage_analysis_service import DamageAnalysisService  # noqa: E402

MARKER = "LINE_TEST_PRIVATE_RESULT_9846"
app = create_app()
app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

gemini = Mock()
service = DamageAnalysisService(gemini)
service.analyze_damage = Mock(wraps=service.analyze_damage)
service.save_analysis_result = Mock(side_effect=AssertionError("Unexpected DB write"))
app.extensions["damage_analysis_service"] = service
app.extensions["chat_service"] = ChatService(gemini)


@app.get("/__line_readonly_test_identity")
def test_identity():
    return jsonify(
        authenticated=bool(current_user.is_authenticated),
        user_id=(int(current_user.user_id) if current_user.is_authenticated else None),
    )


def as_user(client, user_id):
    """Simulate post-LINE-login Flask-Login state (no OAuth/network calls)."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def analysis_csrf(client):
    response = client.get("/analysis")
    assert response.status_code == 200, f"/analysis returned {response.status_code}"
    match = re.search(r'data-csrf-token="([^"]+)"', response.get_data(as_text=True))
    assert match, "Analysis CSRF token not found"
    return match.group(1)


def form_csrf(response):
    assert response.status_code == 200, f"GET returned {response.status_code}"
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.get_data(as_text=True))
    assert match, "Form CSRF token not found"
    return match.group(1)


def private_session(client, line_id, report_id):
    """Seed ephemeral session state, never insert records into MySQL."""
    with client.session_transaction() as sess:
        sess["report_id"] = report_id
        sess["user_id"] = -999  # stale legacy ID must not authorize access
        sess.pop("guest_analysis", None)
        sess["analysis_result"] = {
            "damage_level": 2, "repair_cost_min": 1000,
            "repair_cost_max": 2000, "description": MARKER,
            "damage_locations": [], "repair_items": [], "photos": [], "is_mock": True,
        }
        sess["analysis_result_context"] = {"report_id": report_id, "user_id": line_id}
        sess["analysis_followup"] = {"question": "PRIVATE_QUESTION_FOR_LINE_USER"}
        sess["analysis_followup_context"] = {
            "report_id": report_id, "user_id": line_id,
            "login_user_id": str(line_id),
        }
        sess["analysis_answers"] = []


with app.app_context():
    if db.engine.dialect.name != "mysql" or db.engine.url.host not in (
        "localhost", "127.0.0.1", "::1"
    ):
        raise RuntimeError("Only local MySQL is allowed")
    dbname = db.session.execute(db.text("SELECT DATABASE()" )).scalar()
    if dbname != "tanouesoftware_db":
        raise RuntimeError("Unexpected database: " + str(dbname))

    linked_ids = db.session.execute(
        select(UserAuth.user_id).where(UserAuth.provider_code == 1)
        .distinct().order_by(UserAuth.user_id.desc())
    ).scalars().all()
    if not linked_ids:
        raise RuntimeError(
            "No LINE-linked account exists in this MySQL DB. "
            "Logging into LINE Developers alone does not create an app user."
        )
    line_id = int(linked_ids[0])
    assert db.session.get(User, line_id) is not None
    foreign_report = db.session.execute(
        select(DamageReport.report_id, Building.user_id)
        .join(Building, DamageReport.building_id == Building.building_id)
        .where(Building.user_id != line_id)
        .order_by(DamageReport.report_id)
    ).first()
    foreign_history = db.session.execute(
        select(AnalysisHistory.analysis_id)
        .join(DamageReport, AnalysisHistory.report_id == DamageReport.report_id)
        .join(Building, DamageReport.building_id == Building.building_id)
        .where(Building.user_id != line_id)
        .order_by(AnalysisHistory.analysis_id)
    ).scalar()
    if not foreign_report or not foreign_history:
        raise RuntimeError("A separate user's report and analysis history are needed for denial tests")
    foreign_report_id, other_id = int(foreign_report[0]), int(foreign_report[1])
    foreign_analysis_id = int(foreign_history)
    own_report_count = db.session.execute(
        select(db.func.count()).select_from(Building).where(Building.user_id == line_id)
    ).scalar_one()
    db.session.rollback()
    db.session.remove()

print("=== LINE-LINKED USER SECURITY TEST ===")
print("Database: tanouesoftware_db @ localhost")
print("LINE-linked test user_id:", line_id)
if len(linked_ids) > 1:
    print("NOTE: Multiple LINE-linked users exist; testing the highest user_id only.")
print("LINE user's building count:", own_report_count)

# 1: Flask-Login resolves the existing LINE-linked MySQL user.
client = app.test_client()
as_user(client, line_id)
who = client.get("/__line_readonly_test_identity")
assert who.status_code == 200 and who.json == {"authenticated": True, "user_id": line_id}
print("TEST 1 LINE-LINKED FLASK-LOGIN IDENTITY: PASS")

# 2: Old session['user_id'] cannot authorize access to another user's report.
with client.session_transaction() as sess:
    sess["report_id"] = foreign_report_id
    sess["user_id"] = other_id
    sess.pop("guest_analysis", None)
token = analysis_csrf(client)
response = client.post(
    "/analysis/run", json={},
    headers={"X-CSRF-Token": token, "Accept": "application/json"}
)
assert response.status_code == 200 and response.is_json
assert response.json.get("status") == "failure", response.json
assert service.analyze_damage.call_args.kwargs["user_id"] == line_id
gemini.judgement_data.assert_not_called()
service.save_analysis_result.assert_not_called()
print("TEST 2 NON-OWNER ANALYSIS BLOCKED BEFORE AI: PASS")

# 3: Another user's saved analysis and chat cannot be read.
response = client.get(f"/chat?analysis_id={foreign_analysis_id}")
assert response.status_code == 404, f"Expected 404, got {response.status_code}"
print("TEST 3 NON-OWNER CHAT HISTORY BLOCKED: PASS")

# 4: Logout removes access to previous result and saved chat.
private_session(client, line_id, foreign_report_id)
logout_page = client.get("/auth/logout")
logout_token = form_csrf(logout_page)
logout_response = client.post(
    "/auth/logout", data={"csrf_token": logout_token}, follow_redirects=False
)
assert logout_response.status_code == 302
assert client.get("/__line_readonly_test_identity").json["authenticated"] is False
result_after = client.get("/analysis/result")
chat_after = client.get(f"/chat?analysis_id={foreign_analysis_id}")
assert result_after.status_code in (302, 303) and MARKER not in result_after.get_data(as_text=True)
assert chat_after.status_code == 403
print("TEST 4 LOGOUT BLOCKS PREVIOUS RESULT AND CHAT: PASS")

# 5: Changing authenticated identity blocks old follow-up POST/GET and result.
switch_client = app.test_client()
as_user(switch_client, line_id)
private_session(switch_client, line_id, foreign_report_id)
prior_followup = switch_client.get("/analysis/followup")
prior_token = form_csrf(prior_followup)
# Simulate the authentication state AFTER account switching. No real OAuth call.
as_user(switch_client, other_id)
post_after_switch = switch_client.post(
    "/analysis/followup",
    data={"answer": "REPLAYED_OLD_ANSWER", "csrf_token": prior_token},
    follow_redirects=False,
)
result_after_switch = switch_client.get("/analysis/result")
view_after_switch = switch_client.get("/analysis/followup")
assert post_after_switch.status_code == 403, f"POST: {post_after_switch.status_code}"
assert result_after_switch.status_code in (302, 303)
assert MARKER not in result_after_switch.get_data(as_text=True)
assert "PRIVATE_QUESTION_FOR_LINE_USER" not in view_after_switch.get_data(as_text=True)
with switch_client.session_transaction() as sess:
    assert not sess.get("analysis_answers")
print("TEST 5 ACCOUNT SWITCH BLOCKS OLD FOLLOWUP AND RESULT: PASS")

service.save_analysis_result.assert_not_called()
print("DB analysis save calls: NONE")
print("=== ALL 5 LINE-LINKED SECURITY TESTS PASSED ===")
print("NOTE: Tests simulate post-login state; real LINE OAuth callback is not tested here.")
