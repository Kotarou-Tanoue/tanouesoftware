"""One-off real LINE OAuth browser flow audit for the existing tanouesoftware app.

Execution (from the project's root directory):
    .\\.venv\\Scripts\\python.exe .\\tests\\test_line_oauth_live_audit.py

The script temporarily runs the project's *actual* Flask app on localhost:5000.
No application source files are modified, and no LINE credentials or tokens are logged.
Open the printed URL in a fresh private/incognito browser window, complete LINE
login, then use the app's logout form. Results print in the PowerShell terminal.

NOTE: This performs actual LINE API requests via the application's existing
callback. The separate negative-case checks use Flask's test client without
calling LINE APIs. On a first-ever login, the existing callback may create a
normal User and UserAuth record; this script itself performs no DB writes.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "app").is_dir():
    raise SystemExit("ERROR: put this file under the project tests/ directory")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import request, session  # noqa: E402
from flask_login import current_user  # noqa: E402

from app import create_app  # noqa: E402
from app.auth.auth_routes import LINE_FLOW_KEY, LINE_FLOW_TTL  # noqa: E402
from app.auth.line_auth_service import LINE_AUTHORIZE_URL, LINE_PROVIDER_CODE  # noqa: E402
from app.models.user_auth import UserAuth  # noqa: E402


def announce(label: str, passed: bool, note: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    suffix = f" ({note})" if note else ""
    print(f"{label}: {status}{suffix}", flush=True)


app = create_app()
app.config.update(TESTING=False, WTF_CSRF_ENABLED=True)

configured = all(
    app.config.get(name)
    for name in ("LINE_CHANNEL_ID", "LINE_CHANNEL_SECRET", "LINE_CALLBACK_URL")
)
if not configured:
    raise SystemExit("FAIL: LINE_CHANNEL_ID / LINE_CHANNEL_SECRET / LINE_CALLBACK_URL not configured")

callback_url = str(app.config["LINE_CALLBACK_URL"])
callback_parts = urlsplit(callback_url)
if callback_parts.scheme not in ("http", "https") or not callback_parts.netloc:
    raise SystemExit("FAIL: Invalid LINE_CALLBACK_URL")
if callback_parts.path != "/auth/line/callback":
    raise SystemExit("FAIL: LINE_CALLBACK_URL path must be /auth/line/callback")


def get_redirect_validation(response, session_flow) -> bool:
    if response.status_code != 302 or not isinstance(session_flow, dict):
        return False
    location = response.headers.get("Location", "")
    parsed = urlsplit(location)
    params = parse_qs(parsed.query)
    required = (
        "client_id", "redirect_uri", "scope", "state", "nonce",
        "response_type", "code_challenge", "code_challenge_method",
    )
    if any(len(params.get(field, [])) != 1 for field in required):
        return False
    verifier = session_flow.get("verifier")
    if not isinstance(verifier, str):
        return False
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return all(
        (
            parsed.scheme == "https",
            parsed.netloc == "access.line.me",
            parsed.path == urlsplit(LINE_AUTHORIZE_URL).path,
            params["client_id"][0] == str(app.config["LINE_CHANNEL_ID"]),
            params["redirect_uri"][0] == callback_url,
            "openid" in params["scope"][0].split(),
            params["response_type"][0] == "code",
            params["state"][0] == session_flow.get("state"),
            params["nonce"][0] == session_flow.get("nonce"),
            params["code_challenge_method"][0] == "S256",
            params["code_challenge"][0] == expected_challenge,
        )
    )


def negative_callback_tests() -> bool:
    """Prove rejection before token exchange: no LINE API calls or DB writes."""
    with app.test_client() as client:
        start = client.get("/auth/line")
        with client.session_transaction() as s:
            flow = dict(s.get(LINE_FLOW_KEY, {}))
        start_ok = get_redirect_validation(start, flow)
        announce("TEST A AUTHORIZE PARAMETERS / STATE / NONCE / PKCE", start_ok)
        if not start_ok:
            return False

        invalid = client.get(
            "/auth/line/callback?state=invalid_test_state&code=invalid_test_code",
            follow_redirects=False,
        )
        with client.session_transaction() as s:
            no_login = not s.get("_user_id")
        invalid_ok = (
            invalid.status_code == 303
            and urlsplit(invalid.headers.get("Location", "")).path == "/auth/login"
            and no_login
        )
        announce("TEST B INVALID STATE REJECTED", invalid_ok)
        if not invalid_ok:
            return False

    with app.test_client() as client:
        start = client.get("/auth/line")
        with client.session_transaction() as s:
            flow = dict(s.get(LINE_FLOW_KEY, {}))
            flow["issued_at"] = time.time() - LINE_FLOW_TTL - 20
            s[LINE_FLOW_KEY] = flow
        if start.status_code != 302:
            announce("TEST C EXPIRED STATE REJECTED", False)
            return False
        # An expired flow must be rejected BEFORE exchanging any fake code.
        expired = client.get(
            "/auth/line/callback",
            query_string={"state": flow["state"], "code": "invalid_test_code"},
            follow_redirects=False,
        )
        with client.session_transaction() as s:
            no_login = not s.get("_user_id")
        expired_ok = (
            expired.status_code == 303
            and urlsplit(expired.headers.get("Location", "")).path == "/auth/login"
            and no_login
        )
        announce("TEST C EXPIRED STATE REJECTED", expired_ok)
        return expired_ok


# The callback tests are invoked AFTER all request hooks have been registered.
# They should not be mistaken for actual browser OAuth events.
audit_active = False

# Werkzeug's regular HTTP request log contains authorization codes in callback
# query strings; suppress it to avoid accidentally copying secrets into logs.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

observed = {
    "started": False,
    "callback": False,
    "identity": False,
    "landing": False,
    "logout": False,
}
last_user_id = None
printed_final = False


@app.after_request
def check_real_browser_flow(response):
    global last_user_id, printed_final

    # The local negative-case checks run through Flask's test client.
    # Never record these as live LINE login attempts.
    if not audit_active:
        return response

    endpoint = request.endpoint
    if endpoint == "auth.line_login":
        ok = get_redirect_validation(response, session.get(LINE_FLOW_KEY))
        observed["started"] = ok
        announce("TEST 1 LIVE LINE AUTHORIZATION START", ok)

    elif endpoint == "auth.line_callback":
        # The real route itself validates state, exchanges the code, verifies
        # LINE's ID token and completes login_user(). We DO NOT mock it here.
        try:
            authenticated = bool(current_user.is_authenticated)
            current_id = int(current_user.user_id) if authenticated else None
            line_linked = (
                bool(
                    UserAuth.query.filter_by(
                        provider_code=LINE_PROVIDER_CODE,
                        user_id=current_id,
                    ).first()
                )
                if authenticated
                else False
            )
        except Exception:
            authenticated = False
            current_id = None
            line_linked = False

        callback_ok = (
            observed["started"]
            and response.status_code == 303
            and urlsplit(response.headers.get("Location", "")).path == "/"
            and authenticated
            and session.get(LINE_FLOW_KEY) is None
        )
        observed["callback"] = callback_ok
        observed["identity"] = callback_ok and line_linked
        last_user_id = current_id if observed["identity"] else None
        announce("TEST 2 REAL CALLBACK / LINE TOKEN VERIFICATION", callback_ok)
        announce(
            "TEST 3 FLASK-LOGIN AND MYSQL LINE IDENTITY",
            observed["identity"],
            f"user_id={last_user_id}" if last_user_id is not None else "",
        )
        if not callback_ok:
            print(
                "  Hint: check LINE channel Tester permissions, callback URL, "
                "browser cookies and Flask warnings (without sharing tokens).",
                flush=True,
            )

    elif endpoint == "index" and observed["identity"] and not observed["landing"]:
        landing_ok = (
            response.status_code == 200
            and bool(current_user.is_authenticated)
            and int(current_user.user_id) == last_user_id
        )
        observed["landing"] = landing_ok
        announce("TEST 4 REDIRECT TO APP STILL AUTHENTICATED", landing_ok)

    elif endpoint == "auth.logout" and request.method == "POST":
        logged_out = (
            response.status_code in (302, 303)
            and not bool(current_user.is_authenticated)
            and not session.get("_user_id")
        )
        observed["logout"] = logged_out
        announce("TEST 5 LOGOUT CLEARS FLASK-LOGIN SESSION", logged_out)

    if all(observed.values()) and not printed_final:
        printed_final = True
        print("\n=== ALL 5 LIVE LINE OAUTH TESTS PASSED ===", flush=True)
        print("No LINE authorization code, ID token or cookie has been printed.", flush=True)

    return response


# All Flask request hooks are now registered. Run negative-case prechecks
# before enabling real-browser event observation or starting the server.
if not negative_callback_tests():
    raise SystemExit("FAILED: local OAuth security prechecks did not pass")
audit_active = True

print("\n=== REAL LINE OAUTH BROWSER + POWERSHELL AUDIT ===", flush=True)
print("Open this URL in a NEW private/incognito browser window:", flush=True)
origin = f"{callback_parts.scheme}://{callback_parts.netloc}"
print(f"  {origin}/auth/line", flush=True)
print("Complete LINE sign-in and return to the app, then open:", flush=True)
print(f"  {origin}/auth/logout", flush=True)
print("Use the logout button on that page (do not simply close the browser).", flush=True)
print("Keep this PowerShell terminal running until the final PASS message.", flush=True)
print("Expected configured callback path: /auth/line/callback", flush=True)
print("NOTE: The configured host must forward requests to THIS Flask process.", flush=True)
print("Press Ctrl+C to stop when done.\n", flush=True)

app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
