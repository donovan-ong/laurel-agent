"""Tests for the embeddable widget's side of the API: Bearer-token sessions, its own login/logout routes, and CORS.

Same approach as test_webapp.py: login calls planner.client.connect, so it is monkeypatched to a FakeClient. The
cookie flow the webapp uses is covered in test_webapp.py and must keep working alongside this one.
"""
import pytest
from fastapi.testclient import TestClient
from test_scenario_runner import FakeClient, calls, reply

import webapp.server as server
from webapp.server import create_app

EXTENSION_ORIGIN = "chrome-extension://" + "a" * 32


def script(number, prompt):
    return reply(text=f"Hello from {number}, you said: {prompt}", steps=calls("get_student_profile"))


@pytest.fixture(autouse=True)
def fake_connect(monkeypatch):
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClient(number, script))


def client() -> TestClient:
    return TestClient(create_app())


def widget_login(c: TestClient, username: str = "demo1") -> dict:
    r = c.post("/api/widget/login", json={"username": username, "password": username})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_widget_login_returns_a_token_and_sets_no_cookie():
    r = client().post("/api/widget/login", json={"username": "demo4", "password": "demo4"})
    body = r.json()
    assert r.status_code == 200 and set(body) == {"token", "username", "student_number"}
    assert body["username"] == "demo4" and body["student_number"] == "S0000004" and len(body["token"]) > 20
    assert "session" not in r.cookies


def test_widget_login_rejects_bad_credentials():
    assert client().post("/api/widget/login", json={"username": "demo1", "password": "wrong"}).status_code == 401
    assert client().post("/api/widget/login", json={}).status_code == 401


def test_widget_login_fails_visibly_when_the_trial_token_has_expired(monkeypatch):
    def expired(number, agent_name=None):
        raise SystemExit(1)
    monkeypatch.setattr(server, "connect", expired)
    r = client().post("/api/widget/login", json={"username": "demo1", "password": "demo1"})
    assert r.status_code == 502 and "expired" in r.json()["detail"]


def test_the_webapps_own_login_response_is_unchanged():
    r = client().post("/api/login", json={"username": "demo1", "password": "demo1"})
    assert r.json() == {"username": "demo1", "student_number": "S0000001"}


def test_a_bearer_token_opens_the_existing_protected_routes():
    c = client()
    headers = widget_login(c, "demo4")
    assert c.get("/api/me", headers=headers).json() == {"logged_in": True, "username": "demo4", "student_number": "S0000004"}
    chat = c.post("/api/chat", json={"message": "hi"}, headers=headers)
    assert chat.status_code == 200 and "you said: hi" in chat.json()["reply"]
    assert c.get("/api/chat/history", headers=headers).status_code == 200
    profile = c.get("/api/profile", headers=headers).json()
    assert profile["found"] is True and profile["student"]["student_number"] == "S0000004"
    week = c.get("/api/week", headers=headers).json()
    assert week["found"] is True and week["name"] == "Casey Delacroix"


def test_no_token_and_a_bad_token_are_rejected():
    c = client()
    assert c.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert c.post("/api/chat", json={"message": "hi"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/api/chat", json={"message": "hi"}, headers={"Authorization": "Basic abc"}).status_code == 401
    assert c.get("/api/me", headers={"Authorization": "Bearer nope"}).json() == {"logged_in": False}


def test_two_widget_logins_are_independent_and_keep_their_own_thread():
    c = client()
    a, b = widget_login(c, "demo1"), widget_login(c, "demo2")
    assert c.get("/api/me", headers=a).json()["student_number"] == "S0000001"
    assert c.get("/api/me", headers=b).json()["student_number"] == "S0000002"
    c.post("/api/chat", json={"message": "one"}, headers=a)
    assert c.get("/api/chat/history", headers=a).json()["thread_id"] is not None
    assert c.get("/api/chat/history", headers=b).json() == {"messages": [], "thread_id": None}  # b never chatted


def test_widget_logout_invalidates_only_that_token():
    c = client()
    a, b = widget_login(c, "demo1"), widget_login(c, "demo2")
    assert c.post("/api/widget/logout", headers=a).json() == {"status": "logged_out"}
    assert c.get("/api/me", headers=a).json() == {"logged_in": False}
    assert c.get("/api/me", headers=b).json()["logged_in"] is True


def test_widget_logout_without_a_token_is_not_an_error():
    assert client().post("/api/widget/logout").status_code == 200


def test_the_cookie_flow_still_works_alongside_bearer():
    c = client()
    c.post("/api/login", json={"username": "demo1", "password": "demo1"})
    assert c.get("/api/me").json()["logged_in"] is True


@pytest.mark.parametrize("origin", ["https://www.rmit.edu.au", "http://localhost:8100", "http://127.0.0.1:5173", EXTENSION_ORIGIN])
def test_cors_preflight_is_allowed_for_the_widgets_origins(origin):
    r = client().options("/api/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                               "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in r.headers


@pytest.mark.parametrize("origin", ["https://evil.example", "https://rmit.edu.au.evil.example", "http://www.rmit.edu.au"])
def test_cors_preflight_is_refused_for_other_origins(origin):
    r = client().options("/api/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_a_simple_cross_origin_response_carries_the_allow_origin_header():
    r = client().get("/api/me", headers={"Origin": "https://www.rmit.edu.au"})
    assert r.headers["access-control-allow-origin"] == "https://www.rmit.edu.au"


# --- /api/session/adopt: the widget's "Laurel" link, staying logged in on the full webapp ---

def test_adopting_a_valid_widget_token_sets_the_webapp_cookie_and_redirects_home():
    c = client()
    token = widget_login(c)["Authorization"].removeprefix("Bearer ")
    r = c.get(f"/api/session/adopt?token={token}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    assert r.cookies["session"] == token
    # The cookie really is the same session: the same client, now carrying only the cookie (its bearer
    # header from widget_login() was never sent to this endpoint), reads /api/me as logged in.
    assert c.get("/api/me").json()["logged_in"] is True


def test_adopting_an_unknown_token_redirects_to_login_without_a_cookie():
    r = client().get("/api/session/adopt?token=not-a-real-token", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"
    assert "session" not in r.cookies


def test_adopting_with_no_token_redirects_to_login():
    r = client().get("/api/session/adopt", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"
