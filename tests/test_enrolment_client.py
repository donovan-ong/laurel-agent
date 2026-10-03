import io
import json
import threading
import time
import urllib.error
from datetime import date

import pytest
import uvicorn
from ibm_watsonx_orchestrate.run.context import AgentRun

from mockapi.server import create_app
from tools import dropping as drop, enrolment as enr, enrolment_client as client
from tools.enrolment_tools import check_drop, check_enrolment, drop_enrolment, list_enrolments, submit_enrolment

KEY = "secret-key-123"
IDS = ["1015", "1102"]


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def configure(monkeypatch, tmp_path, url="http://service.invalid"):
    path = tmp_path / "service_config.json"
    path.write_text(json.dumps({"url": url, "key": KEY}), encoding="utf-8")
    monkeypatch.setattr(client, "CONFIG_PATH", path)


class Reply:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def read(self):
        return self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_transport(monkeypatch, behave):
    """Replace urlopen. behave(request) returns a Reply or raises. Every request is recorded."""
    seen = []

    def urlopen(request, timeout=None):
        seen.append({"method": request.get_method(), "url": request.full_url, "headers": dict(request.header_items()),
                     "body": json.loads(request.data) if request.data else None, "timeout": timeout})
        result = behave(request)
        if result.status >= 400:
            raise urllib.error.HTTPError(request.full_url, result.status, "error", {}, io.BytesIO(result.read()))
        return result
    monkeypatch.setattr(client.urllib.request, "urlopen", urlopen)
    return seen


def all_tools(number="S0000008"):
    """Each tool called once, as the agent would, for a student who can do all of it."""
    return {
        "check_enrolment": lambda: check_enrolment.fn(context=ctx(number), class_ids=IDS),
        "submit_enrolment": lambda: submit_enrolment.fn(context=ctx(number), class_ids=IDS, check_id=enr.check_id(number, IDS), student_confirmed=True),
        "list_enrolments": lambda: list_enrolments.fn(context=ctx(number)),
        "check_drop": lambda: check_drop.fn(context=ctx(number), course_id="COSC2148", term="2027-S1"),
        "drop_enrolment": lambda: drop_enrolment.fn(context=ctx(number), course_id="COSC2148", term="2027-S1",
                                                   check_id=drop.check_id(number, "COSC2148", "2027-S1"), student_confirmed=True),
    }


# Configuration

def test_no_configuration_means_no_service(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "CONFIG_PATH", tmp_path / "missing.json")
    assert client.config() is None and client.configured() is False


@pytest.mark.parametrize("content", ["not json", "{}", '{"url": "http://x"}', '{"key": "k"}', '{"url": "", "key": "k"}'])
def test_a_broken_or_incomplete_configuration_means_no_service(monkeypatch, tmp_path, content):
    path = tmp_path / "service_config.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(client, "CONFIG_PATH", path)
    assert client.configured() is False


# When the service cannot answer, nothing is reported as done

FAILURES = {
    "connection refused": lambda request: (_ for _ in ()).throw(urllib.error.URLError(ConnectionRefusedError())),
    "timeout": lambda request: (_ for _ in ()).throw(TimeoutError()),
    "an OS error": lambda request: (_ for _ in ()).throw(OSError("network is unreachable")),
    "a proxy error page": lambda request: Reply(502, b"<html>Bad gateway</html>"),
    "a tunnel that is down": lambda request: Reply(200, b"<html>Tunnel not found</html>"),
    "a server error": lambda request: Reply(500, {"detail": "boom"}),
    "a rejected key": lambda request: Reply(401, {"error": {"code": "UNAUTHORISED"}}),
    "the wrong kind of answer": lambda request: Reply(200, {"ok": True}),
    "a list instead of an object": lambda request: Reply(200, []),
}


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("tool", list(all_tools()))
def test_an_unreachable_service_is_reported_and_nothing_is_claimed(monkeypatch, tmp_path, failure, tool):
    configure(monkeypatch, tmp_path)
    fake_transport(monkeypatch, FAILURES[failure])
    result = all_tools()[tool]()
    assert result["found"] is False
    assert "unavailable" in result["reason"] and "Nothing was changed" in result["reason"]
    text = json.dumps(result)
    assert "reference" not in text and "SIM-" not in text and "DROP-" not in text
    assert "enrolled" not in result.get("status", "") and "dropped" not in result.get("status", "")
    assert KEY not in text and "service.invalid" not in text


# What is sent

def test_requests_carry_the_key_a_request_id_and_the_student_from_the_context(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    seen = fake_transport(monkeypatch, lambda request: Reply(200, {"eligible": True, "reasons": []}))
    check_enrolment.fn(context=ctx("S0000003"), class_ids=IDS, availability={"busy": []})
    (request,) = seen
    assert request["method"] == "POST" and request["url"] == "http://service.invalid/v1/enrolments/check"
    assert request["headers"]["X-api-key"] == KEY and len(request["headers"]["X-request-id"]) == 8
    assert request["body"] == {"student_number": "S0000003", "class_ids": IDS, "availability": {"busy": []}}
    assert request["timeout"] == client.TIMEOUT


def test_the_student_number_comes_only_from_the_login(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    seen = fake_transport(monkeypatch, lambda request: Reply(200, {"enrolments": []}))
    list_enrolments.fn(context=ctx("S0000002"))
    check_drop_calls = fake_transport(monkeypatch, lambda request: Reply(200, {"can_drop": False, "reasons": []}))
    check_drop.fn(context=ctx("S0000002"), course_id="COSC2148", term="2027-S1")
    assert seen[0]["url"].endswith("/v1/students/S0000002/enrolments")
    assert check_drop_calls[0]["url"].endswith("/v1/students/S0000002/enrolments/COSC2148/2027-S1/drop-check")


def test_nobody_logged_in_never_reaches_the_service(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    seen = fake_transport(monkeypatch, lambda request: Reply(200, {}))
    for call in (lambda: check_enrolment.fn(context=None, class_ids=IDS),
                 lambda: submit_enrolment.fn(context=AgentRun(request_context={}), class_ids=IDS, check_id="x", student_confirmed=True),
                 lambda: drop_enrolment.fn(context=None, course_id="COSC2148", term="2027-S1", check_id="x", student_confirmed=True)):
        assert call()["found"] is False
    assert seen == []


@pytest.mark.parametrize("course,term", [("../../admin/reset", "2027-S1"), ("COSC2148", "2027-S1/../../x"), ("..", "2027-S1"),
                                         ("COSC2148", ".."), ("COSC 2148", "2027-S1"), ("COSC2148?key=1", "2027-S1"), ("", "2027-S1"),
                                         ("COSC2148", ""), ("COSC2148", "S1"), ("COSC2148%2F", "2027-S1")])
def test_a_course_or_term_that_could_change_the_path_is_refused_before_sending(monkeypatch, tmp_path, course, term):
    configure(monkeypatch, tmp_path)
    seen = fake_transport(monkeypatch, lambda request: Reply(200, {}))
    result = check_drop.fn(context=ctx("S0000008"), course_id=course, term=term)
    assert result["found"] is False and "Give the" in result["reason"]
    assert drop_enrolment.fn(context=ctx("S0000008"), course_id=course, term=term, check_id="x", student_confirmed=True)["found"] is False
    assert seen == []


def test_the_services_own_refusals_are_passed_on_with_who_served_them(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    refusal = {"status": "refused", "error": {"code": "CLASS_FULL", "message": "full"}, "simulated": True, "notice": enr.NOTICE}
    fake_transport(monkeypatch, lambda request: Reply(409, refusal))
    result = all_tools()["submit_enrolment"]()
    assert result == {**refusal, "served_by": client.SERVED_BY}
    dropped = {"status": "refused", "error": {"code": "NOT_ENROLLED", "message": "no"}, "simulated": True, "notice": enr.NOTICE}
    fake_transport(monkeypatch, lambda request: Reply(404, dropped))
    assert all_tools()["drop_enrolment"]()["error"]["code"] == "NOT_ENROLLED"


def test_a_check_through_the_service_still_has_found_a_source_and_who_served_it(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    fake_transport(monkeypatch, lambda request: Reply(200, {"eligible": True, "reasons": [], "check_id": "abc"}))
    result = all_tools()["check_enrolment"]()
    assert result["found"] is True and result["served_by"] == client.SERVED_BY and result["source"]["file"] == "timetable.json"


# End to end through a real HTTP server

@pytest.fixture
def live(monkeypatch, tmp_path):
    app = create_app(KEY, today=lambda: date(2026, 9, 22))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    port = server.servers[0].sockets[0].getsockname()[1]
    configure(monkeypatch, tmp_path, f"http://127.0.0.1:{port}")
    yield app
    server.should_exit = True
    thread.join(5)


def test_the_tools_enrol_list_and_drop_through_the_service(live):
    number = "S0000001"
    checked = check_enrolment.fn(context=ctx(number), class_ids=IDS)
    assert checked["found"] and checked["eligible"] is True and checked["served_by"] == client.SERVED_BY
    done = submit_enrolment.fn(context=ctx(number), class_ids=IDS, check_id=checked["check_id"], student_confirmed=True)
    assert done["status"] == "enrolled" and done["reference"].startswith("SIM-") and done["served_by"] == client.SERVED_BY
    again = submit_enrolment.fn(context=ctx(number), class_ids=IDS, check_id=checked["check_id"], student_confirmed=True)
    assert again["status"] == "refused" and again["error"]["code"] == "ALREADY_ENROLLED"
    listed = list_enrolments.fn(context=ctx(number))
    assert [e["course_id"] for e in listed["enrolments"]] == ["COSC2148"] and listed["served_by"] == client.SERVED_BY
    preview = check_drop.fn(context=ctx(number), course_id="COSC2148", term="2027-S1")
    assert preview["can_drop"] is True and preview["consequences"]["fee_outcome"] == "avoided"
    gone = drop_enrolment.fn(context=ctx(number), course_id="COSC2148", term="2027-S1", check_id=preview["check_id"], student_confirmed=True)
    assert gone["status"] == "dropped" and gone["reference"].startswith("DROP-")
    assert list_enrolments.fn(context=ctx(number))["enrolments"] == []


def test_the_dashboard_log_shows_the_tools_calls_in_order(live):
    number = "S0000008"
    check_drop.fn(context=ctx(number), course_id="COSC2148", term="2027-S1")
    drop_enrolment.fn(context=ctx(number), course_id="COSC2148", term="2027-S1",
                      check_id=drop.check_id(number, "COSC2148", "2027-S1"), student_confirmed=True)
    events = live.state.bus.since(0)
    assert [(e["method"], e["kind"], e["student"], e["status"]) for e in events] == [
        ("GET", "drop_check", number, 200), ("DELETE", "drop", number, 200)]
    assert all(e["request_id"] and len(e["request_id"]) == 8 for e in events)


def test_a_refusal_from_the_service_is_not_an_outage(live):
    result = drop_enrolment.fn(context=ctx("S0000004"), course_id="COSC2110", term="2026-S2",
                               check_id=drop.check_id("S0000004", "COSC2110", "2026-S2"), student_confirmed=True)
    assert result["status"] == "refused" and result["error"]["code"] == "DROP_DEADLINE_PASSED"


def test_a_wrong_key_is_reported_as_unavailable(live, monkeypatch, tmp_path):
    (tmp_path / "service_config.json").write_text(json.dumps({"url": json.loads(client.CONFIG_PATH.read_text())["url"], "key": "wrong"}))
    result = check_enrolment.fn(context=ctx("S0000001"), class_ids=IDS)
    assert result["found"] is False and "unavailable" in result["reason"] and "wrong" not in json.dumps(result)


def test_when_the_service_stops_the_tools_say_so(monkeypatch, tmp_path):
    app = create_app(KEY)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    configure(monkeypatch, tmp_path, f"http://127.0.0.1:{port}")
    assert check_enrolment.fn(context=ctx("S0000001"), class_ids=IDS)["found"] is True
    server.should_exit = True
    thread.join(5)
    for name, call in all_tools("S0000001").items():
        result = call()
        assert result["found"] is False and "Nothing was changed" in result["reason"], name
        assert "reference" not in json.dumps(result)
