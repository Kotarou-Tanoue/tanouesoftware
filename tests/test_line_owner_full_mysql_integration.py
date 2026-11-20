r"""LINE-linked owner's analysis -> follow-up -> result -> chat/MySQL integration.

Place in tests/; from project root run:
    .\.venv\Scripts\python.exe .\tests\test_line_owner_full_mysql_integration.py

SAFETY: local tanouesoftware_db ONLY. Creates a uniquely marked temporary building,
report, location, analysis history and chat history for an existing LINE-linked user;
deletes ONLY the temporary fixture and descendants in finally. No account changes.
Flask-Login post-OAuth identity is simulated in this test client. NO real LINE OAuth,
Gemini or S3 calls. Deterministic synthetic analysis/chat content is deliberately
sent through the normal persistence branches and removed afterwards.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select, text

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "app").is_dir() and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.analysis.chat_service import ChatService  # noqa: E402
from app.analysis.damage_analysis_service import DamageAnalysisService  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisHistory, Building, BuildingType, ChatHistory, DamageLocation,
    DamagePhoto, DamageReport, DamageStatus, EarthquakeRelation,
    LocationSeverity, User, UserAuth,
)

USER_ID = 4   # Verify this user has LINE provider_code=1 before creating data.
MARKER = "LINE_OWNER_TEST_" + uuid4().hex
QUESTION = "QUESTION_" + MARKER
ANSWER = "ANSWER_" + MARKER
FOLLOWUP_ANSWER = "建物の外壁にひび割れがあります（テスト用）。"
LOCATION_DESCRIPTION = "LOCATION_DETAIL_" + MARKER


def passed(title, detail=""):
    print(title + ": PASS" + (f" ({detail})" if detail else ""))


def require_http(response, code, label):
    assert response.status_code == code, (
        f"{label}: expected HTTP {code}, received {response.status_code}; "
        f"response={response.get_data(as_text=True)[:300]!r}"
    )
    passed(label, f"HTTP {code}")


def csrf_token(response, *, analysis=False):
    html = response.get_data(as_text=True)
    pattern = (
        r'data-csrf-token="([^"]+)"'
        if analysis else r'name="csrf_token"\s+value="([^"]+)"'
    )
    match = re.search(pattern, html)
    assert match, "CSRF token missing from HTML"
    return match.group(1)


def count_tables():
    db.session.remove()
    return {
        model.__tablename__: db.session.scalar(select(func.count()).select_from(model))
        for model in (Building, DamageReport, DamageLocation, AnalysisHistory, ChatHistory)
    }


class DeterministicTestAI:
    """Test-only input: not genuine AI; exercise the *real* MySQL write branch."""
    is_mock = False  # Test fixture MUST persist, unlike production development mock.

    def __init__(self):
        self.report_id = None
        self.location_id = None
        self.chat_calls = 0
        self.analyze_calls = 0

    def judgement_data(self, data, answers):
        self.analyze_calls += 1
        assert data["owner_user_id"] == USER_ID
        assert data["report"]["report_id"] == self.report_id
        assert {x["location_id"] for x in data["locations"]} == {self.location_id}
        return len(answers) == 0

    def generate_followup_questions(self, data, answers):
        return "【テスト用】外壁の状態を教えてください。"

    def generate_analysis_result(self, data, answers):
        assert len(answers) == 1
        assert answers[0]["answer"] == FOLLOWUP_ANSWER
        return {
            "damage_level": 3,
            "repair_cost_min": 30000,
            "repair_cost_max": 80000,
            "description": MARKER,
            "damage_locations": [{
                "location_id": self.location_id,
                "location_name": "テスト用外壁",
                "description": LOCATION_DESCRIPTION,
                "severity": 2,
            }],
            "repair_items": [],
            "photos": [],
        }

    def generate_chat_response(self, result, question, history):
        self.chat_calls += 1
        assert question == QUESTION
        assert result["description"] == MARKER
        return ANSWER


def cleanup(app):
    """Remove ONLY this run's Building and its related test rows."""
    with app.app_context():
        db.session.rollback()
        db.session.remove()
        try:
            # Require BOTH the unique marker and the expected owner.
            buildings = db.session.scalars(
                select(Building).where(
                    Building.building_name == MARKER,
                    Building.user_id == USER_ID,
                )
            ).all()
            for building in buildings:
                bid = building.building_id
                report_ids = db.session.scalars(
                    select(DamageReport.report_id).where(DamageReport.building_id == bid)
                ).all()
                for rid in report_ids:
                    analysis_ids = db.session.scalars(
                        select(AnalysisHistory.analysis_id).where(AnalysisHistory.report_id == rid)
                    ).all()
                    if analysis_ids:
                        db.session.execute(delete(ChatHistory).where(ChatHistory.analysis_id.in_(analysis_ids)))
                    db.session.execute(delete(AnalysisHistory).where(AnalysisHistory.report_id == rid))
                    location_ids = db.session.scalars(
                        select(DamageLocation.location_id).where(DamageLocation.report_id == rid)
                    ).all()
                    if location_ids:
                        db.session.execute(delete(DamagePhoto).where(DamagePhoto.location_id.in_(location_ids)))
                    db.session.execute(delete(DamageLocation).where(DamageLocation.report_id == rid))
                    db.session.execute(delete(DamageReport).where(DamageReport.report_id == rid))
                db.session.execute(delete(Building).where(
                    Building.building_id == bid, Building.user_id == USER_ID,
                    Building.building_name == MARKER,
                ))
            db.session.commit()
            still_there = db.session.scalar(select(func.count()).select_from(Building).where(
                Building.building_name == MARKER, Building.user_id == USER_ID,
            ))
            assert still_there == 0, "Temporary building remains after cleanup"
            passed("CLEANUP", f"removed {len(buildings)} temporary building(s)")
        except Exception:
            db.session.rollback()
            print(f"CLEANUP FAILED: inspect test building_name={MARKER!r}")
            raise
        finally:
            db.session.remove()


def main():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    fake_ai = DeterministicTestAI()
    # Services, DB, auth and CSRF are the application's real implementations.
    app.extensions["damage_analysis_service"] = DamageAnalysisService(fake_ai)
    app.extensions["chat_service"] = ChatService(fake_ai)

    print("=== LINE OWNER ANALYSIS + CHAT MYSQL INTEGRATION TEST ===")
    print("Marker:", MARKER)

    with app.app_context():
        assert db.engine.dialect.name == "mysql", "MySQL required"
        assert db.engine.url.host in ("localhost", "127.0.0.1", "::1"), (
            "Only a locally hosted development MySQL database is permitted"
        )
        db_name = db.session.execute(text("SELECT DATABASE()")).scalar()
        assert db_name == "tanouesoftware_db", f"Unexpected DB: {db_name}"
        assert db.session.get(User, USER_ID) is not None, "User ID 4 does not exist"
        line_linked = db.session.scalar(select(func.count()).select_from(UserAuth).where(
            UserAuth.user_id == USER_ID, UserAuth.provider_code == 1,
        ))
        assert line_linked >= 1, "User ID 4 is not linked to LINE (provider_code=1)"
        assert db.session.get(BuildingType, 1) is not None
        assert db.session.get(DamageStatus, 0) is not None
        assert db.session.get(EarthquakeRelation, 2) is not None
        assert db.session.get(LocationSeverity, 2) is not None
        before = count_tables()
        passed("TEST 1 LOCAL MYSQL / LINE-LINKED USER", f"{db_name} @ {db.engine.url.host}; user_id={USER_ID}")

    completed = False
    try:
        # Create a test-owned building, damage report and location. No real users' data changed.
        with app.app_context():
            building = Building(
                user_id=USER_ID,
                building_name=MARKER,
                prefecture="熊本県",
                city="熊本市",
                built_year=2000,
                building_type_code=1,
            )
            db.session.add(building)
            db.session.flush()
            building_id = building.building_id
            report = DamageReport(
                building_id=building_id,
                door_window_status=0,
                noise_status=0,
                tilt_status=0,
            )
            db.session.add(report)
            db.session.flush()
            report_id = report.report_id
            location = DamageLocation(
                report_id=report_id,
                location_name="テスト用外壁",
                location_type="外壁",
                damage_type="ひび割れ",
                earthquake_relation=2,
                description=None,
                severity=None,
            )
            db.session.add(location)
            db.session.flush()
            location_id = location.location_id
            db.session.commit()
            fake_ai.report_id = report_id
            fake_ai.location_id = location_id
            passed("TEST 2 TEMP BUILDING / REPORT / LOCATION CREATED", f"building={building_id}, report={report_id}, location={location_id}")

        # Flask-Login session is reconstructed; we DO NOT call actual LINE OAuth here.
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess["_user_id"] = str(USER_ID)
            sess["_fresh"] = True
            sess["report_id"] = report_id
            sess.pop("guest_analysis", None)
            sess["user_id"] = 2  # Stale legacy id must NOT replace Flask-Login identity.
        page = owner.get("/analysis")
        require_http(page, 200, "TEST 3 OWNER ANALYSIS SCREEN")
        run_token = csrf_token(page, analysis=True)

        response = owner.post("/analysis/run", json={}, headers={
            "X-CSRF-Token": run_token, "Accept": "application/json",
        })
        require_http(response, 200, "TEST 4 ANALYSIS START")
        assert response.is_json and response.json["status"] == "followup", response.json
        page = owner.get(response.json["redirect_url"])
        require_http(page, 200, "TEST 5 FOLLOWUP QUESTION")
        assert "【テスト用】外壁の状態" in page.get_data(as_text=True)
        followup_token = csrf_token(page)

        response = owner.post("/analysis/followup", data={
            "answer": FOLLOWUP_ANSWER, "csrf_token": followup_token,
        }, follow_redirects=False)
        require_http(response, 303, "TEST 6 FOLLOWUP ANSWER")
        with owner.session_transaction() as sess:
            assert sess.get("analysis_resume_pending") is True
            assert len(sess.get("analysis_answers", [])) == 1
            assert "analysis_result" not in sess

        page = owner.get("/analysis?resume=1")
        require_http(page, 200, "TEST 7 RESUME SCREEN")
        resume_token = csrf_token(page, analysis=True)
        response = owner.post("/analysis/run", json={}, headers={
            "X-CSRF-Token": resume_token, "Accept": "application/json",
        })
        require_http(response, 200, "TEST 8 ANALYSIS COMPLETED")
        assert response.is_json and response.json["status"] == "result", response.json
        with owner.session_transaction() as sess:
            analysis_id = sess.get("analysis_id")
            assert type(analysis_id) is int and analysis_id > 0
            assert sess["analysis_result_context"] == {"report_id": report_id, "user_id": USER_ID}
        assert fake_ai.analyze_calls == 3

        with app.app_context():
            db.session.remove()
            stored = db.session.get(AnalysisHistory, analysis_id)
            updated_location = db.session.get(DamageLocation, location_id)
            assert stored is not None and stored.report_id == report_id
            assert stored.damage_level == 3 and stored.description == MARKER
            assert stored.repair_cost_min == 30000 and stored.repair_cost_max == 80000
            assert updated_location.description == LOCATION_DESCRIPTION
            assert updated_location.severity == 2
            passed("TEST 9 REAL MYSQL ANALYSIS / DAMAGE LOCATION SAVE", f"analysis_id={analysis_id}")

        page = owner.get("/analysis/result")
        require_http(page, 200, "TEST 10 RESULT SCREEN")
        assert MARKER in page.get_data(as_text=True)

        page = owner.get(f"/chat?analysis_id={analysis_id}")
        require_http(page, 200, "TEST 11 OWNER CHAT SCREEN")
        token = csrf_token(page)
        response = owner.post("/chat/message", data={
            "question": QUESTION, "csrf_token": token,
        }, follow_redirects=False)
        require_http(response, 303, "TEST 12 CHAT POST")
        assert fake_ai.chat_calls == 1

        with app.app_context():
            db.session.remove()
            rows = db.session.scalars(select(ChatHistory).where(
                ChatHistory.analysis_id == analysis_id,
                ChatHistory.user_question == QUESTION,
            )).all()
            assert len(rows) == 1 and rows[0].ai_answer == ANSWER
            passed("TEST 13 REAL MYSQL CHAT HISTORY READBACK", f"chat_id={rows[0].chat_id}")

        page = owner.get(response.headers["Location"])
        require_http(page, 200, "TEST 14 SAVED CHAT DISPLAY")
        assert QUESTION in page.get_data(as_text=True)
        assert ANSWER in page.get_data(as_text=True)

        # Owner isolation also checked on the newly created analysis history.
        stranger = app.test_client()
        with stranger.session_transaction() as sess:
            sess["_user_id"] = "3"
            sess["_fresh"] = True
        response = stranger.get(f"/chat?analysis_id={analysis_id}")
        require_http(response, 404, "TEST 15 NON-OWNER CHAT ACCESS BLOCKED")
        with app.app_context():
            db.session.remove()
            try:
                service = app.extensions["damage_analysis_service"]
                service.save_analysis_result(
                    report_id=report_id,
                    result=fake_ai.generate_analysis_result({}, [{"answer": FOLLOWUP_ANSWER}]),
                    user_id=3,
                )
            except PermissionError:
                passed("TEST 16 NON-OWNER ANALYSIS SAVE BLOCKED")
            else:
                raise AssertionError("Non-owner's save was accepted")
            finally:
                db.session.rollback()

        completed = True
    finally:
        # Also handles failed/partial fixture creation.
        cleanup(app)
        with app.app_context():
            after = count_tables()
        for table, old in before.items():
            current = after[table]
            print(f"{table}: {old} -> {current}")
            assert current == old, f"{table} count did not return to its original value"
        passed("TEST 17 TEMPORARY DATA CLEANUP / ORIGINAL COUNTS RESTORED")

    if completed:
        print("\n=== ALL LINE OWNER FULL MYSQL INTEGRATION TESTS PASSED ===")
        print("NOTE: LINE OAuth, Gemini API and S3 were NOT called; only the local MySQL and app flows were tested.")


if __name__ == "__main__":
    main()
