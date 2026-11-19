"""Local-MySQL integration test for result-question chat.

Execute from the tanouesoftware project root with:
    .venv\\Scripts\\python.exe <path-to-this-file>

Changes only this test's own AnalysisHistory/ChatHistory records, removes them
on exit, and does not call the Gemini API or edit application files.
"""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from app import create_app
from app.analysis.chat_service import ChatService
from app.extensions import db
from app.models import AnalysisHistory, ChatHistory, DamageReport, User

MARKER = "CHAT_MYSQL_TEST_" + uuid4().hex
QUESTION = "QUESTION_" + MARKER
ANSWER = "ANSWER_" + MARKER
GUEST_QUESTION = "GUEST_" + MARKER
GUEST_ANSWER = "GUEST_ANSWER_" + MARKER


class TestResponseGenerator:
    # The false mock flag exercises the DB-save branch in ChatService.
    # The generated response is STILL fixed test text, never a real AI answer.
    is_mock = False

    def __init__(self):
        self.calls = 0

    def generate_chat_response(self, analysis_result, question, chat_history):
        assert isinstance(analysis_result, dict) and analysis_result
        self.calls += 1
        if question == QUESTION:
            assert analysis_result["description"] == MARKER
            return ANSWER
        if question == GUEST_QUESTION:
            return GUEST_ANSWER
        raise AssertionError("Unexpected question in test generator")


def passed(label, details=""):
    print(f"{label}: PASS" + (f" ({details})" if details else ""))


def expect_http(response, code, label):
    assert response.status_code == code, (
        f"{label}: expected HTTP {code}, got {response.status_code}; "
        f"body={response.get_data(as_text=True)[:250]!r}"
    )
    passed(label, f"HTTP {code}")


def get_csrf(response):
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"', response.get_data(as_text=True)
    )
    assert match, "CSRF token was not found in the HTML"
    return match.group(1)


def login(client, user_id):
    page = client.get("/auth/login/dev")
    assert page.status_code == 200
    response = client.post(
        "/auth/login/dev",
        data={"user_id": str(user_id), "csrf_token": get_csrf(page)},
        follow_redirects=False,
    )
    assert response.status_code == 302, f"Login returned HTTP {response.status_code}"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(user_id)


def logout(client):
    page = client.get("/auth/logout")
    assert page.status_code == 200
    response = client.post(
        "/auth/logout",
        data={"csrf_token": get_csrf(page)}, follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert not sess.get("_user_id")


def chat_count(app):
    # Do NOT keep app.app_context() active while making HTTP requests.
    # Doing that can cache Flask-Login's current_user across test clients.
    with app.app_context():
        db.session.remove()
        return db.session.scalar(select(func.count()).select_from(ChatHistory))


def cleanup(app):
    """Remove only this run's uniquely marked analysis and its chat rows."""
    with app.app_context():
        db.session.rollback()
        db.session.remove()
        try:
            ids = db.session.scalars(
                select(AnalysisHistory.analysis_id).where(
                    AnalysisHistory.description == MARKER
                )
            ).all()
            if ids:
                db.session.execute(
                    delete(ChatHistory).where(ChatHistory.analysis_id.in_(ids))
                )
                db.session.execute(
                    delete(AnalysisHistory).where(AnalysisHistory.analysis_id.in_(ids))
                )
            db.session.commit()
            remaining = db.session.scalars(
                select(AnalysisHistory.analysis_id).where(
                    AnalysisHistory.description == MARKER
                )
            ).all()
            assert not remaining
            passed("CLEANUP", f"removed temporary analysis IDs: {ids}")
        except Exception:
            db.session.rollback()
            print("CLEANUP FAILED: examine analysis_history.description =", MARKER)
            raise
        finally:
            db.session.remove()


def run():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    generator = TestResponseGenerator()
    # Only this Flask test instance uses the deterministic response generator.
    # Real ChatService, real Flask-Login, CSRF and MySQL remain enabled.
    app.extensions["chat_service"] = ChatService(generator)

    print("=== RESULT CHAT MYSQL INTEGRATION TEST ===")
    print("Marker:", MARKER)

    # Database guard and test-data creation only, before HTTP test requests.
    with app.app_context():
        assert db.engine.dialect.name == "mysql", "MySQL is required"
        assert db.engine.url.host in ("localhost", "127.0.0.1", "::1"), (
            "Only local development MySQL is allowed"
        )
        name = db.session.execute(text("SELECT DATABASE()")).scalar()
        assert name == "tanouesoftware_db", f"Wrong database: {name!r}"
        report = db.session.get(DamageReport, 1)
        assert report is not None and report.building is not None
        assert report.building.user_id == 2, "report_id=1 must belong to user_id=2"
        assert db.session.get(User, 2) is not None
        assert db.session.get(User, 3) is not None
        original_analysis_count = db.session.scalar(
            select(func.count()).select_from(AnalysisHistory)
        )
        original_chat_count = db.session.scalar(
            select(func.count()).select_from(ChatHistory)
        )
        passed("DATABASE CHECK", f"{name} @ {db.engine.url.host}")

    completed = False
    try:
        with app.app_context():
            temp_analysis = AnalysisHistory(
                report_id=1,
                damage_level=3,
                repair_cost_min=30000,
                repair_cost_max=80000,
                description=MARKER,
            )
            db.session.add(temp_analysis)
            db.session.flush()
            analysis_id = temp_analysis.analysis_id
            db.session.commit()
            passed("TEST 1 TEMP ANALYSIS CREATED", f"analysis_id={analysis_id}")

        # Actual authentication and chat screen.
        owner = app.test_client()
        login(owner, 2)
        passed("TEST 2 OWNER LOGIN", "user_id=2")
        page = owner.get(f"/chat?analysis_id={analysis_id}")
        expect_http(page, 200, "TEST 3 CHAT SCREEN")
        html = page.get_data(as_text=True)
        assert "分析結果について質問" in html and 'name="question"' in html
        token = get_csrf(page)
        assert chat_count(app) == original_chat_count

        # CSRF blocks writes, even before the test fake AI is reached.
        response = owner.post("/chat/message", data={"question": QUESTION})
        expect_http(response, 400, "TEST 4 MISSING CSRF")
        response = owner.post(
            "/chat/message", data={"question": QUESTION, "csrf_token": "INVALID"}
        )
        expect_http(response, 400, "TEST 5 INVALID CSRF")
        assert chat_count(app) == original_chat_count and generator.calls == 0

        response = owner.post(
            "/chat/message",
            data={"question": QUESTION, "csrf_token": token},
            follow_redirects=False,
        )
        expect_http(response, 303, "TEST 6 QUESTION SENT / SAVED")
        assert generator.calls == 1
        assert chat_count(app) == original_chat_count + 1
        with app.app_context():
            db.session.remove()
            rows = db.session.scalars(
                select(ChatHistory).where(
                    ChatHistory.analysis_id == analysis_id,
                    ChatHistory.user_question == QUESTION,
                )
            ).all()
            assert len(rows) == 1 and rows[0].ai_answer == ANSWER
            passed("TEST 7 PERSISTENT MYSQL READBACK", f"chat_id={rows[0].chat_id}")

        page = owner.get(response.headers["Location"])
        expect_http(page, 200, "TEST 8 CHAT HISTORY DISPLAY")
        assert QUESTION in page.get_data(as_text=True)
        assert ANSWER in page.get_data(as_text=True)
        passed("TEST 8 CONTENT VERIFIED")

        anonymous = app.test_client()
        response = anonymous.get(f"/chat?analysis_id={analysis_id}")
        expect_http(response, 403, "TEST 9 ANONYMOUS ACCESS BLOCKED")
        assert QUESTION not in response.get_data(as_text=True)

        stranger = app.test_client()
        login(stranger, 3)
        response = stranger.get(f"/chat?analysis_id={analysis_id}")
        expect_http(response, 404, "TEST 10 NON-OWNER VIEW BLOCKED")
        assert QUESTION not in response.get_data(as_text=True)

        # Even a forged saved analysis ID must be rejected on POST.
        stranger_token = get_csrf(stranger.get("/auth/logout"))
        with stranger.session_transaction() as sess:
            sess["chat_scope"] = {
                "kind": "saved", "analysis_id": analysis_id, "user_id": 3,
            }
        before_calls = generator.calls
        response = stranger.post(
            "/chat/message",
            data={"question": QUESTION, "csrf_token": stranger_token},
        )
        expect_http(response, 404, "TEST 11 NON-OWNER WRITE BLOCKED")
        assert generator.calls == before_calls
        assert chat_count(app) == original_chat_count + 1

        # A changed login must not reuse the old saved chat session.
        logout(owner)
        login(owner, 3)
        switched_token = get_csrf(owner.get("/auth/logout"))
        before_calls = generator.calls
        response = owner.post(
            "/chat/message",
            data={"question": QUESTION, "csrf_token": switched_token},
        )
        assert response.status_code in (403, 404), (
            f"Old chat allowed after user switch: HTTP {response.status_code}"
        )
        assert generator.calls == before_calls
        assert chat_count(app) == original_chat_count + 1
        passed("TEST 12 ACCOUNT SWITCH BLOCKED", f"HTTP {response.status_code}")

        # Guest chats remain in their own server session, never in chat_history.
        guest = app.test_client()
        with guest.session_transaction() as sess:
            sess.pop("report_id", None)
            sess["guest_analysis"] = {"building": {"building_name": "TEST GUEST"}}
            sess["analysis_result"] = {
                "damage_level": 2, "description": "TEST GUEST ANALYSIS",
                "repair_cost_min": None, "repair_cost_max": None, "is_mock": True,
            }
            sess["analysis_result_context"] = {"report_id": None, "user_id": None}
        page = guest.get("/chat")
        expect_http(page, 200, "TEST 13 GUEST SCREEN")
        response = guest.post(
            "/chat/message",
            data={"question": GUEST_QUESTION, "csrf_token": get_csrf(page)},
            follow_redirects=False,
        )
        expect_http(response, 303, "TEST 14 GUEST MESSAGE")
        page = guest.get("/chat")
        assert page.status_code == 200
        assert GUEST_QUESTION in page.get_data(as_text=True)
        assert GUEST_ANSWER in page.get_data(as_text=True)
        assert chat_count(app) == original_chat_count + 1
        passed("TEST 15 GUEST MESSAGE NOT SAVED")

        completed = True
    finally:
        cleanup(app)
        with app.app_context():
            current_analysis_count = db.session.scalar(
                select(func.count()).select_from(AnalysisHistory)
            )
            current_chat_count = db.session.scalar(
                select(func.count()).select_from(ChatHistory)
            )
        print(f"AnalysisHistory: {original_analysis_count} -> {current_analysis_count}")
        print(f"ChatHistory: {original_chat_count} -> {current_chat_count}")
        assert current_analysis_count == original_analysis_count
        assert current_chat_count == original_chat_count
        passed("TEST 16 ORIGINAL COUNTS RESTORED")

    if completed:
        print("\n=== ALL RESULT CHAT MYSQL TESTS PASSED ===")


if __name__ == "__main__":
    run()
