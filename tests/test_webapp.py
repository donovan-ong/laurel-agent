"""Tests for the web frontend's API.

login calls planner.client.connect to build a ChatClient, so every test here monkeypatches webapp.server.connect
to hand back a FakeClient instead — reusing the FakeClient/reply()/calls() trio from test_scenario_runner.py
(the scenario runner's own tests use the same trio) rather than hitting the live agent or needing a trial token.
The trace toggle itself is a pure frontend/client-side concern and needs no test here; the only backend
guarantee is that `trace` is always present in a chat reply, which test_chat_happy_path_... covers.
"""
import re

import pytest
from fastapi.testclient import TestClient
from test_scenario_runner import FakeClient, calls, reply

import webapp.server as server
from webapp.server import create_app


def script(number, prompt):
    return reply(text=f"Hello from {number}, you said: {prompt}", steps=calls("get_student_profile"))


class FakeThreads:
    """A minimal stand-in for ThreadsClient, only get_thread_messages, for the reload-recovery tests."""
    def __init__(self, by_thread=None):
        self.by_thread = by_thread or {}

    def get_thread_messages(self, thread_id):
        return {"data": self.by_thread.get(thread_id, [])}


class FakeClientWithHistory(FakeClient):
    def __init__(self, number, script, threads_client=None):
        super().__init__(number, script)
        self.threads_client = threads_client or FakeThreads()


@pytest.fixture(autouse=True)
def fake_connect(monkeypatch):
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClient(number, script))


def client() -> TestClient:
    return TestClient(create_app())


def login(c: TestClient, username: str = "demo1") -> TestClient:
    c.post("/api/login", json={"username": username, "password": username})
    return c


def test_login_succeeds_with_a_valid_demo_account():
    r = client().post("/api/login", json={"username": "demo1", "password": "demo1"})
    assert r.status_code == 200
    assert r.json() == {"username": "demo1", "student_number": "S0000001"}
    assert "session" in r.cookies


def test_login_fails_with_a_wrong_password():
    r = client().post("/api/login", json={"username": "demo1", "password": "wrong"})
    assert r.status_code == 401
    assert "session" not in r.cookies


def test_login_fails_with_an_unknown_username():
    assert client().post("/api/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_login_fails_with_an_empty_body():
    assert client().post("/api/login", json={}).status_code == 401


def test_me_reports_logged_out_with_no_cookie():
    r = client().get("/api/me")
    assert r.status_code == 200 and r.json() == {"logged_in": False}


def test_me_reports_logged_in_after_login():
    c = client()
    c.post("/api/login", json={"username": "demo4", "password": "demo4"})
    assert c.get("/api/me").json() == {"logged_in": True, "username": "demo4", "student_number": "S0000004"}


def test_me_reports_logged_out_with_a_bad_cookie():
    c = client()
    c.cookies.set("session", "not-a-real-token")
    assert c.get("/api/me").json() == {"logged_in": False}


def test_logout_clears_the_session():
    c = client()
    c.post("/api/login", json={"username": "demo1", "password": "demo1"})
    r = c.post("/api/logout")
    assert r.status_code == 200 and r.json() == {"status": "logged_out"}
    assert c.get("/api/me").json() == {"logged_in": False}


def test_logout_without_a_session_is_not_an_error():
    assert client().post("/api/logout").status_code == 200


def test_two_logins_get_independent_sessions():
    a, b = client(), client()
    a.post("/api/login", json={"username": "demo1", "password": "demo1"})
    b.post("/api/login", json={"username": "demo2", "password": "demo2"})
    assert a.get("/api/me").json()["student_number"] == "S0000001"
    assert b.get("/api/me").json()["student_number"] == "S0000002"
    a.post("/api/logout")
    assert a.get("/api/me").json() == {"logged_in": False}
    assert b.get("/api/me").json()["student_number"] == "S0000002"  # unaffected by a's logout


def test_login_fails_visibly_when_the_agent_cannot_be_found(monkeypatch):
    from planner.client import ChatError

    def broken(number, agent_name=None):
        raise ChatError("Agent study_planner_agent was not found in the active environment.")
    monkeypatch.setattr(server, "connect", broken)
    r = client().post("/api/login", json={"username": "demo1", "password": "demo1"})
    assert r.status_code == 502 and "session" not in r.cookies


def test_login_fails_visibly_when_the_trial_token_has_expired(monkeypatch):
    # The Orchestrate SDK calls sys.exit(1) itself on an expired token, instead of raising something
    # catchable — this must not become an unhandled 500.
    def expired(number, agent_name=None):
        raise SystemExit(1)
    monkeypatch.setattr(server, "connect", expired)
    r = client().post("/api/login", json={"username": "demo1", "password": "demo1"})
    assert r.status_code == 502 and "expired" in r.json()["detail"] and "session" not in r.cookies


# build_trace: the FakeClient/calls() trio only produces tool_calls entries (no tool_response), so this
# is tested directly against the real step_history shape (step_details -> tool_calls / tool_response).

def test_build_trace_merges_a_call_with_its_response():
    steps = [{"step_details": [
        {"type": "tool_calls", "tool_calls": [{"name": "get_fees", "args": {"course_ids": ["COSC2148"]}}]},
        {"type": "tool_response", "name": "get_fees", "content": '{"found": true}'},
    ]}]
    assert server.build_trace(steps) == [
        {"tool": "get_fees", "args": {"course_ids": ["COSC2148"]}, "result_preview": '{"found": true}'}]


def test_build_trace_handles_several_calls_in_one_step():
    steps = [{"step_details": [
        {"type": "tool_calls", "tool_calls": [{"name": "a", "args": {}}, {"name": "b", "args": {}}]},
        {"type": "tool_response", "name": "a", "content": "1"},
        {"type": "tool_response", "name": "b", "content": "2"},
    ]}]
    trace = server.build_trace(steps)
    assert [(t["tool"], t["result_preview"]) for t in trace] == [("a", "1"), ("b", "2")]


def test_build_trace_truncates_a_long_result():
    long_content = "x" * 1000
    steps = [{"step_details": [
        {"type": "tool_calls", "tool_calls": [{"name": "a", "args": {}}]},
        {"type": "tool_response", "name": "a", "content": long_content},
    ]}]
    preview = server.build_trace(steps)[0]["result_preview"]
    assert len(preview) == server.TRACE_CHARS + len(" ...") and preview.endswith(" ...")


def test_build_trace_on_empty_or_missing_steps():
    assert server.build_trace([]) == [] and server.build_trace(None) == []


# Chat

def test_chat_requires_login():
    assert client().post("/api/chat", json={"message": "hi"}).status_code == 401


def test_chat_happy_path_returns_reply_trace_and_thread_id():
    c = login(client())
    r = c.post("/api/chat", json={"message": "What is my GPA?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Hello from S0000001, you said: What is my GPA?"
    assert body["trace"] == [{"tool": "get_student_profile", "args": {}, "result_preview": None}]
    assert body["thread_id"] == "thread-1" and body["seconds"] == 1.0


def test_chat_rejects_an_empty_message():
    c = login(client())
    assert c.post("/api/chat", json={"message": "  "}).status_code == 400
    assert c.post("/api/chat", json={}).status_code == 400


def test_chat_reuses_the_thread_id_across_messages(monkeypatch):
    asked = []

    def tracking_script(number, prompt):
        asked.append(prompt)
        return reply(text="ok")
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClient(number, tracking_script))
    c = login(client())
    first = c.post("/api/chat", json={"message": "one"}).json()
    second = c.post("/api/chat", json={"message": "two"}).json()
    assert first["thread_id"] == second["thread_id"] == "thread-1"
    assert asked == ["one", "two"]


def test_chat_surfaces_a_run_failure_as_a_visible_error(monkeypatch):
    from planner.client import ChatError

    def failing_script(number, prompt):
        raise ChatError("The run failed: platform error")
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClient(number, failing_script))
    c = login(client())
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 502 and "platform error" in r.json()["detail"]


def test_each_session_gets_its_own_chat_client_and_conversation():
    a, b = login(client(), "demo1"), login(client(), "demo2")
    ra = a.post("/api/chat", json={"message": "hi"}).json()
    rb = b.post("/api/chat", json={"message": "hi"}).json()
    assert ra["reply"].startswith("Hello from S0000001") and rb["reply"].startswith("Hello from S0000002")


def test_a_second_login_does_not_reuse_the_first_sessions_thread(monkeypatch):
    # Calling connect() at login builds a fresh client, so a fresh login always starts thread_id at None.
    c = login(client())
    c.post("/api/chat", json={"message": "one"})
    c.post("/api/logout")
    login(c)
    r = c.post("/api/chat", json={"message": "two"})
    assert r.status_code == 200


# Profile

def test_profile_requires_login():
    assert client().get("/api/profile").status_code == 401


def test_profile_returns_the_logged_in_students_own_fields():
    c = login(client(), "demo4")
    r = c.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    student = body["student"]
    assert (student["student_number"], student["name"], student["program_code"]) == ("S0000004", "Casey Delacroix", "BH013P26")
    assert {e["course_id"] for e in student["current_enrolments"]} == {"COSC2110", "COSC2673"}
    assert all("title" in e for e in student["current_enrolments"])
    assert body["source"]["file"] == "students.json"


def test_profile_never_returns_another_students_data():
    a, b = login(client(), "demo1"), login(client(), "demo4")
    assert a.get("/api/profile").json()["student"]["student_number"] == "S0000001"
    assert b.get("/api/profile").json()["student"]["student_number"] == "S0000004"


def test_profile_does_not_call_the_chat_agent(monkeypatch):
    calls_made = []
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: calls_made.append(number) or FakeClient(number, script))
    c = login(client())
    calls_made.clear()  # ignore the connect() call made at login itself
    c.get("/api/profile")
    assert calls_made == []  # connect()/ask() never touched for a profile lookup



def test_week_requires_login():
    assert client().get("/api/week").status_code == 401


def test_week_lists_the_logged_in_students_own_items_most_urgent_first():
    c = login(client(), "demo4")
    body = c.get("/api/week", params={"on": "2026-10-03"}).json()
    assert body["found"] is True and body["week_label"] == "Week 10, Semester 2 2026"
    assert body["items"][0]["urgency"] == "overdue"
    assert "Assignment 2 for Data Mining" in [i["title"] for i in body["items"]]
    assert all(i["prompt"] for i in body["items"])


def test_week_does_not_call_the_chat_agent(monkeypatch):
    calls_made = []
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: calls_made.append(number) or FakeClient(number, script))
    c = login(client())
    calls_made.clear()
    c.get("/api/week")
    assert calls_made == []

# The SPA shell: a single built React app serves every page and client-side route; React itself decides
# what to render, and redirects if not logged in, so the server-sent HTML is the same for all of these.

@pytest.mark.parametrize("path", ["/", "/login", "/profile", "/profile/whatever", "/anything"])
def test_every_path_serves_the_spa_shell(path):
    r = client().get(path)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and '<div id="root">' in r.text


def test_a_missing_build_fails_visibly(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DIST_DIR", tmp_path / "no-such-dist")
    r = client().get("/")
    assert r.status_code == 500 and "npm run build" in r.json()["detail"]


# Chat history (reload recovery)

def test_chat_history_requires_login():
    assert client().get("/api/chat/history").status_code == 401


def test_chat_history_is_empty_before_any_message():
    c = login(client())
    r = c.get("/api/chat/history")
    assert r.status_code == 200 and r.json() == {"messages": [], "thread_id": None}


def test_chat_history_recovers_a_conversation_after_a_reload(monkeypatch):
    thread = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello!", "step_history": calls("get_student_profile")},
    ]
    threads_client = FakeThreads({"thread-1": thread})
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClientWithHistory(number, script, threads_client))
    c = login(client())
    c.post("/api/chat", json={"message": "one"})  # sets session["thread_id"] to "thread-1" (reply()'s fixed id)
    r = c.get("/api/chat/history")
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == "thread-1"
    assert body["messages"] == [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "hello!", "trace": [{"tool": "get_student_profile", "args": {}, "result_preview": None}]},
    ]


def test_chat_history_degrades_gracefully_when_recovery_fails(monkeypatch):
    class BrokenThreads:
        def get_thread_messages(self, thread_id):
            raise RuntimeError("boom")
    monkeypatch.setattr(server, "connect", lambda number, agent_name=None: FakeClientWithHistory(number, script, BrokenThreads()))
    c = login(client())
    c.post("/api/chat", json={"message": "one"})
    r = c.get("/api/chat/history")
    assert r.status_code == 200 and r.json()["messages"] == []  # no crash, just nothing recovered


def test_recover_history_skips_malformed_entries_and_tolerates_no_trace():
    thread = [
        {"role": "system", "content": "ignored"},  # not user/assistant: skipped
        "not a dict",  # malformed: skipped
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},  # no step_history at all: trace defaults to []
    ]
    client_ = FakeClientWithHistory("n", script, FakeThreads({"t": thread}))
    assert server.recover_history(client_, "t") == [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "ok", "trace": []},
    ]


def test_recover_history_returns_empty_for_an_unknown_thread():
    client_ = FakeClientWithHistory("n", script, FakeThreads())
    assert server.recover_history(client_, "no-such-thread") == []


def test_built_assets_are_served():
    # The exact hashed filenames change every build, so ask the built index.html which ones it references
    # rather than hardcoding them.
    index = (server.DIST_DIR / "index.html").read_text(encoding="utf-8")
    paths = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index)
    assert paths, "the build should reference at least one /assets/... file"
    for path in paths:
        r = client().get(path)
        assert r.status_code == 200, path


def test_a_nonexistent_asset_404s_rather_than_falling_back_to_the_spa_shell():
    r = client().get("/assets/does-not-exist.js")
    assert r.status_code == 404


def test_a_root_level_built_file_like_the_favicon_is_served_as_itself():
    r = client().get("/favicon.svg")
    assert r.status_code == 200 and "svg" in r.headers["content-type"]
