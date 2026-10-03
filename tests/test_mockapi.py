import asyncio
import json
import threading
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from ibm_watsonx_orchestrate.run.context import AgentRun

from mockapi.events import EventBus, stream
from mockapi.server import STATUS, create_app
from tools import dropping as drop, enrolment as enr
from tools.enrolment_tools import check_drop, check_enrolment, drop_enrolment, submit_enrolment

KEY = "test-key"
H = {"X-API-Key": KEY}
DAY = date(2026, 9, 22)
WORK = {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}
LOCAL_ONLY = ("found", "source")


@pytest.fixture
def api():
    return TestClient(create_app(KEY, today=lambda: DAY))


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def strip(result):
    return {k: v for k, v in result.items() if k not in LOCAL_ONLY}


def enrol_body(number, ids, confirmed=True, availability=None):
    return {"student_number": number, "class_ids": ids, "check_id": enr.check_id(number, ids),
            "student_confirmed": confirmed, "availability": availability}


def do_drop(api, number, course, term, confirmed=True, check_id=None):
    return api.request("DELETE", f"/v1/students/{number}/enrolments/{course}/{term}", headers=H, json={
        "check_id": check_id if check_id is not None else drop.check_id(number, course, term), "student_confirmed": confirmed})


# Keys

def test_health_needs_no_key_and_says_it_is_simulated(api):
    r = api.get("/health")
    assert r.status_code == 200 and r.json()["simulated"] is True and r.json()["today"] == "2026-09-22"


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/v1/enrolments/check", {}), ("POST", "/v1/enrolments", {}),
    ("GET", "/v1/students/S0000001/enrolments", None),
    ("GET", "/v1/students/S0000008/enrolments/COSC2148/2027-S1/drop-check", None),
    ("DELETE", "/v1/students/S0000008/enrolments/COSC2148/2027-S1", {})])
def test_every_api_route_needs_the_key(api, method, path, body):
    for headers in ({}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}):
        r = api.request(method, path, headers=headers, json=body)
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORISED"


def test_the_key_is_never_echoed_in_a_rejection(api):
    r = api.get("/v1/students/S0000001/enrolments", headers={"X-API-Key": "wrong-secret"})
    assert "wrong-secret" not in r.text and KEY not in r.text


# Parity with the local tools

CASES = [(n, ids, av) for n in [f"S000000{i}" for i in range(1, 9)]
         for ids in (["1015", "1102"], ["1193", "1194"], ["1015", "1195"], ["1015", "1015"], ["9999", "1102"], ["1106", "1110"])
         for av in (None, WORK)]


def test_check_gives_the_same_answer_as_the_local_tool_for_every_case(api):
    assert len(CASES) == 96
    eligible = [check_enrolment.fn(context=ctx(n), class_ids=i, availability=a)["eligible"] for n, i, a in CASES]
    assert 8 < sum(eligible) < 88  # the cases include both answers
    for number, ids, availability in CASES:
        local = check_enrolment.fn(context=ctx(number), class_ids=ids, availability=availability)
        remote = api.post("/v1/enrolments/check", headers=H, json={"student_number": number, "class_ids": ids, "availability": availability})
        assert remote.status_code == 200 and remote.json() == strip(local), (number, ids, availability)


def test_enrol_gives_the_same_answer_as_the_local_tool_when_nothing_has_happened_yet():
    for number, ids, availability in CASES[::3]:
        api = TestClient(create_app(KEY, today=lambda: DAY))
        local = submit_enrolment.fn(context=ctx(number), class_ids=ids, check_id=enr.check_id(number, ids),
                                    student_confirmed=True, availability=availability)
        remote = api.post("/v1/enrolments", headers=H, json=enrol_body(number, ids, True, availability))
        assert remote.json() == strip(local), (number, ids)
        assert remote.status_code == (201 if local["status"] == "enrolled" else STATUS[local["error"]["code"]])


def test_drop_check_gives_the_same_answer_as_the_local_tool(api, monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: DAY)
    for number, course, term in [("S0000008", "COSC2148", "2027-S1"), ("S0000008", "COSC2462", "2027-S1"),
                                 ("S0000004", "COSC2110", "2026-S2"), ("S0000005", "COSC2462", "2026-S2"),
                                 ("S0000001", "COSC2148", "2027-S1"), ("S0000007", "INTE2402", "2026-S2")]:
        local = check_drop.fn(context=ctx(number), course_id=course, term=term)
        remote = api.get(f"/v1/students/{number}/enrolments/{course}/{term}/drop-check", headers=H)
        assert remote.status_code == 200 and remote.json() == strip(local), (number, course)


def test_drop_gives_the_same_answer_as_the_local_tool(monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: DAY)
    for number, course, term, confirmed in [("S0000008", "COSC2148", "2027-S1", True), ("S0000008", "COSC2148", "2027-S1", False),
                                            ("S0000004", "COSC2110", "2026-S2", True), ("S0000001", "COSC2148", "2027-S1", True)]:
        api = TestClient(create_app(KEY, today=lambda: DAY))
        local = drop_enrolment.fn(context=ctx(number), course_id=course, term=term,
                                  check_id=drop.check_id(number, course, term), student_confirmed=confirmed)
        remote = do_drop(api, number, course, term, confirmed)
        assert remote.json() == strip(local), (number, course, confirmed)


# Enrolling changes what the service remembers

IDS = ["1015", "1102"]


def test_enrolling_returns_201_a_reference_and_the_notice(api):
    r = api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "enrolled" and body["reference"].startswith("SIM-") and "SIMULATION" in body["notice"]


def test_enrolling_twice_is_refused_as_already_enrolled(api):
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS)).status_code == 201
    again = api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_ENROLLED"
    check = api.post("/v1/enrolments/check", headers=H, json={"student_number": "S0000001", "class_ids": IDS}).json()
    assert check["eligible"] is False and check["reasons"][0]["code"] == "ALREADY_ENROLLED"


def test_the_list_shows_the_record_and_what_was_enrolled_here(api):
    before = api.get("/v1/students/S0000001/enrolments", headers=H).json()
    assert before["enrolments"] == []
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    after = api.get("/v1/students/S0000001/enrolments", headers=H).json()
    (e,) = after["enrolments"]
    assert (e["course_id"], e["term"], e["source"]) == ("COSC2148", "2027-S1", "made through this service")
    assert e["reference"].startswith("SIM-") and e["lecture"]["class_id"] == "1015" and e["workshop"]["class_id"] == "1102"
    robin = api.get("/v1/students/S0000008/enrolments", headers=H).json()["enrolments"]
    assert {x["source"] for x in robin} == {"student record"} and all(x["reference"] is None for x in robin)


def test_one_students_enrolment_is_not_in_another_students_list(api):
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    assert api.get("/v1/students/S0000002/enrolments", headers=H).json()["enrolments"] == []


def test_a_refused_enrolment_changes_nothing(api):
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS, confirmed=False)).status_code == 400
    bad = enrol_body("S0000001", IDS)
    bad["check_id"] = "0" * 16
    assert api.post("/v1/enrolments", headers=H, json=bad).json()["error"]["code"] == "INVALID_CHECK"
    assert api.get("/v1/students/S0000001/enrolments", headers=H).json()["enrolments"] == []


def test_refusals_map_to_http_statuses(api):
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", ["1015", "1015"])).status_code == 422
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000007", ["1015", "1102"])).status_code in (403, 422)
    full = api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", ["1193", "1194"]))
    assert full.status_code == 409 and full.json()["error"]["code"] == "CLASS_FULL"
    closed = api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", ["1193", "1195"]))
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "ENROLMENT_CLOSED"


def test_unknown_students_and_bad_bodies(api):
    r = api.post("/v1/enrolments/check", headers=H, json={"student_number": "S9999999", "class_ids": IDS})
    assert r.status_code == 404 and r.json()["error"]["code"] == "STUDENT_NOT_FOUND"
    assert api.get("/v1/students/S9999999/enrolments", headers=H).status_code == 404
    assert api.post("/v1/enrolments/check", headers=H, json={"class_ids": IDS}).status_code == 404
    assert api.post("/v1/enrolments/check", headers=H, content="not json").status_code == 400
    assert api.post("/v1/enrolments/check", headers=H, json={"student_number": "S0000001", "class_ids": IDS,
                                                              "availability": {"busy": "always"}}).status_code == 400


def test_a_confirmation_that_is_not_the_boolean_true_is_refused(api):
    for value in ("yes", 1, "true", None):
        body = enrol_body("S0000001", IDS)
        body["student_confirmed"] = value
        r = api.post("/v1/enrolments", headers=H, json=body)
        assert r.status_code == 400 and r.json()["error"]["code"] == "NOT_CONFIRMED"


# Seats

def test_a_class_fills_as_students_enrol_and_a_drop_frees_a_seat(api, data_copy):
    path = data_copy / "timetable.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for offering in data:
        for comp in offering["components"]:
            for o in comp["options"]:
                if o["class_id"] == "1102":
                    o["seats_taken"] = o["seats_total"] - 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS)).status_code == 201
    full = api.post("/v1/enrolments", headers=H, json=enrol_body("S0000002", IDS))
    assert full.status_code == 409 and full.json()["error"]["code"] == "CLASS_FULL"
    assert do_drop(api, "S0000001", "COSC2148", "2027-S1").status_code == 200
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000002", IDS)).status_code == 201


def test_dropping_a_record_enrolment_frees_its_seats(api):
    state = lambda: api.get("/admin/state.json", headers=H).json()
    assert state()["seats"] == {}
    assert do_drop(api, "S0000008", "COSC2148", "2027-S1").status_code == 200
    assert state()["seats"] == {"1015": -1, "1102": -1}
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000008", IDS)).status_code == 201
    assert state()["seats"] == {}


# Dropping

def test_dropping_returns_200_a_reference_and_removes_the_enrolment(api):
    r = do_drop(api, "S0000008", "COSC2148", "2027-S1")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "dropped" and body["reference"].startswith("DROP-")
    assert body["consequences"]["fee_outcome"] == "avoided" and "SIMULATION" in body["notice"]
    left = api.get("/v1/students/S0000008/enrolments", headers=H).json()["enrolments"]
    assert [e["course_id"] for e in left] == ["COSC2462"]
    check = api.get("/v1/students/S0000008/enrolments/COSC2148/2027-S1/drop-check", headers=H).json()
    assert check["can_drop"] is False and check["reasons"][0]["code"] == "NOT_ENROLLED"
    again = do_drop(api, "S0000008", "COSC2148", "2027-S1")
    assert again.status_code == 404 and again.json()["error"]["code"] == "NOT_ENROLLED"


def test_a_class_enrolled_here_can_be_dropped_and_enrolled_again(api):
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    assert do_drop(api, "S0000001", "COSC2148", "2027-S1").status_code == 200
    assert api.get("/v1/students/S0000001/enrolments", headers=H).json()["enrolments"] == []
    assert api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS)).status_code == 201


def test_a_drop_after_the_deadline_is_refused_and_keeps_the_enrolment(api):
    r = do_drop(api, "S0000004", "COSC2110", "2026-S2")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DROP_DEADLINE_PASSED"
    assert len(api.get("/v1/students/S0000004/enrolments", headers=H).json()["enrolments"]) == 4


def test_a_drop_needs_confirmation_and_the_right_check_id(api):
    assert do_drop(api, "S0000008", "COSC2148", "2027-S1", confirmed=False).status_code == 400
    r = do_drop(api, "S0000008", "COSC2148", "2027-S1", check_id="wrong")
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_CHECK"
    assert api.request("DELETE", "/v1/students/S0000008/enrolments/COSC2148/2027-S1", headers=H).json()["error"]["code"] == "NOT_CONFIRMED"
    assert len(api.get("/v1/students/S0000008/enrolments", headers=H).json()["enrolments"]) == 2


def test_the_drop_rules_use_the_date_the_service_was_given():
    early = TestClient(create_app(KEY, today=lambda: date(2026, 9, 1)))
    r = early.get("/v1/students/S0000004/enrolments/COSC2110/2026-S2/drop-check", headers=H).json()
    assert r["can_drop"] is True and r["consequences"]["fee_outcome"] == "still_payable"


# Reset and the request log

def test_reset_clears_the_memory_and_the_log(api):
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    do_drop(api, "S0000008", "COSC2148", "2027-S1")
    assert api.post("/admin/reset", headers=H).json() == {"status": "reset"}
    assert api.get("/v1/students/S0000001/enrolments", headers=H).json()["enrolments"] == []
    assert len(api.get("/v1/students/S0000008/enrolments", headers=H).json()["enrolments"]) == 2
    assert api.get("/admin/state.json", headers=H).json()["seats"] == {}
    kinds = [e["kind"] for e in api.get("/admin/events.json", headers=H).json()["events"]]
    assert kinds[0] == "reset"


def test_every_request_is_logged_with_its_fields(api):
    api.post("/v1/enrolments/check", headers={**H, "X-Request-Id": "abc-1"}, json={"student_number": "S0000001", "class_ids": IDS})
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    api.get("/v1/students/S0000001/enrolments", headers=H)
    api.get("/v1/students/S0000008/enrolments/COSC2148/2027-S1/drop-check", headers=H)
    do_drop(api, "S0000008", "COSC2148", "2027-S1")
    events = api.get("/admin/events.json", headers=H).json()["events"]
    assert [e["kind"] for e in events] == ["check", "enrol", "list", "drop_check", "drop"]
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    first = events[0]
    assert (first["method"], first["path"], first["student"], first["status"], first["request_id"]) == (
        "POST", "/v1/enrolments/check", "S0000001", 200, "abc-1")
    assert first["ms"] >= 0 and first["summary"] == "eligible=true  classes 1015 + 1102" and first["response"]["eligible"] is True
    assert events[1]["summary"].startswith("ENROLLED SIM-") and events[1]["status"] == 201
    assert events[2]["summary"] == "1 enrolment"
    assert "fee avoided" in events[3]["summary"] and events[4]["summary"].startswith("DROPPED DROP-")
    assert events[4]["request"]["student_confirmed"] is True


def test_rejected_requests_are_logged_but_the_key_is_not(api):
    api.get("/v1/students/S0000001/enrolments", headers={"X-API-Key": "wrong-secret"})
    (event,) = api.get("/admin/events.json", headers=H).json()["events"]
    assert event["status"] == 401 and "wrong-secret" not in json.dumps(event) and KEY not in json.dumps(event)


def test_only_the_last_events_are_kept():
    bus = EventBus(keep=3)
    for i in range(5):
        bus.publish({"n": i})
    assert [e["n"] for e in bus.since(0)] == [2, 3, 4] and [e["id"] for e in bus.since(3)] == [4, 5]


# Dashboard and stream

def test_the_dashboard_and_admin_views_need_the_key(api):
    for path in ("/", "/admin/events", "/admin/events.json", "/admin/state.json"):
        assert api.get(path).status_code == 401
        assert api.get(path, params={"key": "wrong"}).status_code == 401
    assert api.post("/admin/reset").status_code == 401
    r = api.get("/", params={"key": KEY})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_state_lists_enrolments_drops_and_seats(api):
    api.post("/v1/enrolments", headers=H, json=enrol_body("S0000001", IDS))
    do_drop(api, "S0000008", "COSC2462", "2027-S1")
    state = api.get("/admin/state.json", params={"key": KEY}).json()
    mine = [e for e in state["enrolments"] if e["student"] == "S0000001"]
    assert mine[0]["reference"].startswith("SIM-") and mine[0]["source"] == "service"
    assert not [e for e in state["enrolments"] if (e["student"], e["course_id"]) == ("S0000008", "COSC2462")]
    assert [(d["student"], d["course_id"]) for d in state["dropped_from_record"]] == [("S0000008", "COSC2462")]
    assert state["seats"] == {"1015": 1, "1102": 1, "1106": -1, "1110": -1}
    assert state["today"] == "2026-09-22" and state["uptime_seconds"] >= 0


async def first_frames(bus, count, after=0):
    out = []
    async for text in stream(bus, after, heartbeat=0.05):
        out.append(text)
        if len(out) == count:
            return out


def test_the_stream_replays_recent_events_then_sends_new_ones():
    bus = EventBus()
    bus.publish({"kind": "check"})
    bus.publish({"kind": "enrol"})
    threading.Timer(0.2, lambda: bus.publish({"kind": "drop"})).start()

    async def run():
        out = []
        async for text in stream(bus, 0, heartbeat=5):
            out.append(text)
            if len(out) == 3:
                return out
    frames = asyncio.run(asyncio.wait_for(run(), 5))
    ids = [int(f.split("\n")[0].removeprefix("id: ")) for f in frames]
    assert ids == [1, 2, 3] and all("event: request" in f for f in frames)
    assert json.loads(frames[2].split("data: ")[1])["kind"] == "drop"


def test_a_reconnecting_stream_resumes_after_the_last_id():
    bus = EventBus()
    for kind in ("a", "b", "c"):
        bus.publish({"kind": kind})
    (frame,) = asyncio.run(asyncio.wait_for(first_frames(bus, 1, after=2), 5))
    assert json.loads(frame.split("data: ")[1])["kind"] == "c"


def test_a_quiet_stream_sends_keep_alives():
    frames = asyncio.run(asyncio.wait_for(first_frames(EventBus(), 2), 5))
    assert frames == [": keep-alive\n\n", ": keep-alive\n\n"]


def test_a_stream_forgets_its_subscriber_when_it_ends():
    bus = EventBus()

    async def run():
        gen = stream(bus, 0, heartbeat=0.05)
        await gen.__anext__()
        assert len(bus.subscribers) == 1
        await gen.aclose()
    asyncio.run(run())
    assert bus.subscribers == []


def test_a_stale_resume_id_from_before_a_restart_replays_from_the_start():
    bus = EventBus()
    bus.publish({"kind": "a"})
    assert bus.last_id() == 1 and EventBus().last_id() == 0
