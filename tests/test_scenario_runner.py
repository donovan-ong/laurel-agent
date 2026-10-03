import json

import pytest

from planner import auth, scenarios
from planner.client import Reply
from planner.scenarios import RunResult, ScenarioError, check_turn, load_scenarios, normalise, run_all, run_scenario, summarise
from tools import common
from tools.student_tools import get_academic_record, get_fees
from tools.calendar_tools import get_current_week, get_key_dates
from ibm_watsonx_orchestrate.run.context import AgentRun


def calls(*names):
    return [{"step_details": [{"type": "tool_calls", "tool_calls": [{"name": n, "args": {}} for n in names]}]}]


def reply(text="ok", steps=None, seconds=1.0):
    return Reply("thread-1", text, steps if steps is not None else calls("get_student_profile"), seconds)


# Checks

def test_normalise_ignores_typography_and_markdown():
    assert normalise("**Semester 2** 2026‑09‑21 – it’s `GPA`") == "semester 2 2026-09-21 - it's gpa"


@pytest.mark.parametrize("checks,text,steps,ok", [
    ({"tools_called": ["get_fees"]}, "x", calls("get_student_profile", "get_fees"), True),
    ({"tools_called": ["get_fees"]}, "x", calls("get_student_profile"), False),
    ({"tools_called_any": [["get_current_week", "get_key_dates"]]}, "x", calls("get_key_dates"), True),
    ({"tools_called_any": [["get_current_week", "get_key_dates"]]}, "x", calls("get_fees"), False),
    ({"tools_not_called": ["get_fees"]}, "x", calls("get_fees"), False),
    ({"tools_not_called": ["get_fees"]}, "x", [], True),
    ({"first_tool": "get_student_profile"}, "x", calls("get_student_profile", "get_fees"), True),
    ({"first_tool": "get_student_profile"}, "x", calls("get_fees", "get_student_profile"), False),
    ({"first_tool": "get_student_profile"}, "x", [], False),
    ({"contains": ["Week 9", "35"]}, "It is **Week 9**, 35 days", None, True),
    ({"contains": ["week 9", "35"]}, "Week 9", None, False),
    ({"contains_any": [["a", "b"], ["c"]]}, "b and c", None, True),
    ({"contains_any": [["a", "b"], ["c"]]}, "b only", None, False),
    ({"not_contains": ["casey"]}, "Casey Delacroix", None, False),
    ({"not_contains": ["casey"]}, "Sam", None, True),
    ({"steps_not_contain": ["S0000004"]}, "x", [{"step_details": [{"type": "tool_response", "content": "S0000004"}]}], False),
    ({"steps_not_contain": ["S0000004"]}, "x", calls("get_student_profile"), True),
    ({"max_seconds": 5}, "x", None, True),
])
def test_each_check_passes_and_fails_as_described(checks, text, steps, ok):
    r = reply(text, steps)
    assert (check_turn(checks, r) == []) is ok, check_turn(checks, r)


def test_slow_and_ungrounded_replies_fail():
    assert "took 9.0s, over 5s" in check_turn({"max_seconds": 5}, reply(seconds=9.0))
    made_up = reply("Week 14, source get_current_week", calls("get_student_profile"))
    assert check_turn({"contains": ["week 14"]}, made_up) == ["cites get_current_week without calling it"]
    assert check_turn({"contains": ["week 14"]}, reply("Week 14 from get_current_week", calls("get_current_week"))) == []


# The shipped scenarios

def test_the_shipped_scenarios_are_valid_and_cover_the_ten_scripted_questions():
    loaded = load_scenarios()
    ids = [s.id for s in loaded]
    assert len(ids) == len(set(ids)) and len(loaded) >= 25
    assert len([s for s in loaded if "nfr01" in s.tags]) == 10
    logins = {a["username"] for a in auth.load_accounts()}
    assert {s.login for s in loaded} <= logins
    assert {"identity", "results", "fees", "access", "keydates", "program", "course", "scope"} <= {t for s in loaded for t in s.tags}


def test_access_scenarios_check_tool_results_for_leaks():
    for s in load_scenarios():
        if "access" in s.tags:
            assert "S0000004" in s.turns[0]["checks"]["steps_not_contain"]


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def test_expected_facts_in_the_scenarios_still_match_the_data():
    """If the data changes, the scenarios that quote it must change too."""
    by_id = {s.id: s.turns[0]["checks"] for s in load_scenarios()}
    record = get_academic_record.fn(context=ctx("S0000004"))
    assert [str(record["gpa"]), str(record["wam"])] == by_id["results_continuing_student"]["contains"][:2]
    failed = get_academic_record.fn(context=ctx("S0000005"))
    assert [str(failed["gpa"]), str(failed["wam"])] == by_id["results_failed_course_counts"]["contains"][:2]
    fee = {n: get_fees.fn(context=ctx(n), course_ids=["COSC2148"])["estimate"]["total"] for n in ("S0000001", "S0000002", "S0000003")}
    assert [f"{int(v):,}" for v in fee.values()] == [
        by_id["fees_hecs_student"]["contains"][0], by_id["fees_full_fee_student"]["contains"][0],
        by_id["fees_international_student"]["contains"][0]]
    assert get_fees.fn(context=ctx("S0000007"))["account"]["balance_due"] == 3600
    on = "2026-09-21"
    week = get_current_week.fn(on_date=on)["teaching_weeks"][0]["week"]
    assert week.lower() == by_id["keydates_week_number"]["contains"][0]
    events = {e["category"]: e for e in get_key_dates.fn(period="2026-S2", on_date=on)["events"] if e["category"] in
              ("assessment_period", "results_release", "census")}
    assert (events["assessment_period"]["date"], events["assessment_period"]["days_until_start"]) == ("2026-10-26", 35)
    assert events["results_release"]["date"] == "2026-11-30" and events["census"]["date"] == "2026-08-31"
    nxt = get_current_week.fn(on_date=on)
    assert nxt["next_break"]["date"] == "2026-12-25" and nxt["next_by_category"]["results_release"]["days_until_start"] == 70
    add = [e for e in get_key_dates.fn(period="2026-S2", category="add_deadline")["events"] if e["applies_to"] == "all_other_schools"]
    assert add[0]["date"] == "2026-08-02"
    courses = {c["course_id"]: c for c in common.load("courses.json")}
    assert courses["COSC2148"]["handbook_code"] == "031749" and courses["COSC3047"]["coordinator"] is None
    assert common.load("programs.json")[0]["total_credit_points"] == 96


# Loading

def write(tmp_path, text):
    path = tmp_path / "s.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("body,message", [
    ("scenarios:\n  - {id: a, login: demo1, prompt: hi, checks: {contains: [x]}}\n  - {id: a, login: demo1, prompt: hi, checks: {contains: [x]}}\n", "duplicated"),
    ("scenarios:\n  - {id: a, login: bob, prompt: hi, checks: {contains: [x]}}\n", "demo account"),
    ("scenarios:\n  - {id: a, login: demo1, prompt: hi, checks: {contain: [x]}}\n", "unknown checks"),
    ("scenarios:\n  - {id: a, login: demo1, checks: {contains: [x]}}\n", "prompt and at least one check"),
    ("scenarios:\n  - {id: a, login: demo1, prompt: hi, checks: {}}\n", "prompt and at least one check"),
    ("scenarios:\n  - {login: demo1, prompt: hi, checks: {contains: [x]}}\n", "missing or duplicated"),
])
def test_bad_scenario_files_are_refused(tmp_path, body, message):
    with pytest.raises(ScenarioError, match=message):
        load_scenarios(write(tmp_path, body))


# Running

class FakeClient:
    def __init__(self, number, script):
        self.number, self.script, self.asked = number, script, []

    def ask(self, prompt, thread_id=None):
        self.asked.append((prompt, thread_id))
        return self.script(self.number, prompt)


def scenario(sid="s", login="demo1", turns=None, tags=()):
    return scenarios.Scenario(sid, login, list(tags), turns or [{"prompt": "Hi", "checks": {"contains": ["hello"]}}])


def test_a_passing_run_uses_the_logged_in_students_number():
    seen = []
    def make(number):
        seen.append(number)
        return FakeClient(number, lambda n, p: reply("Hello Sam", calls("get_student_profile"), 2.0))
    r = run_scenario(scenario(login="demo4"), 1, make)
    assert r.passed and r.failures == [] and seen == ["S0000004"] and r.tools == ["get_student_profile"] and r.seconds == 2.0


def test_a_failing_run_lists_why():
    r = run_scenario(scenario(turns=[{"prompt": "Hi", "checks": {"contains": ["week 9"], "tools_called": ["get_fees"]}}]),
                     1, lambda n: FakeClient(n, lambda n_, p: reply("Week 14")))
    assert not r.passed and "reply lacks 'week 9'" in r.failures and "did not call get_fees" in r.failures


def test_multi_turn_scenarios_keep_one_thread_and_name_the_failing_turn():
    turns = [{"prompt": "one", "checks": {"contains": ["a"]}}, {"prompt": "two", "checks": {"contains": ["zzz"]}}]
    client = FakeClient("S0000001", lambda n, p: reply("a", calls("get_student_profile"), 1.5))
    r = run_scenario(scenario(turns=turns), 1, lambda n: client)
    assert client.asked == [("one", None), ("two", "thread-1")]
    assert r.failures == ["turn 2: reply lacks 'zzz'"] and r.seconds == 3.0 and len(r.replies) == 2


def test_an_error_in_one_run_does_not_stop_the_others():
    def make(number):
        raise RuntimeError("platform down")
    r = run_scenario(scenario(), 1, make)
    assert not r.passed and r.failures == ["error: RuntimeError: platform down"]


def test_run_all_repeats_in_order_and_reports_each_result():
    done = []
    scripts = lambda n: FakeClient(n, lambda n_, p: reply("hello", calls("get_student_profile"), 1.0))
    chosen = [scenario("first"), scenario("second")]
    results = run_all(chosen, repeat=3, workers=4, make_client=scripts, on_result=done.append)
    assert [(r.scenario, r.run) for r in results] == [("first", 1), ("first", 2), ("first", 3),
                                                        ("second", 1), ("second", 2), ("second", 3)]
    assert len(done) == 6 and all(r.passed for r in results)


def test_summary_counts_passes_times_and_tags():
    chosen = [scenario("a", tags=["nfr01"]), scenario("b", tags=["nfr01", "x"]), scenario("c")]
    results = [RunResult("a", 1, True, seconds=10.0), RunResult("a", 2, True, seconds=20.0),
               RunResult("b", 1, True, seconds=30.0), RunResult("b", 2, False, ["reply lacks 'z'"], seconds=40.0),
               RunResult("c", 1, False, ["error: boom"])]
    s = summarise(chosen, results)
    rows = {r["scenario"]: r for r in s["rows"]}
    assert (rows["a"]["passed"], rows["a"]["median_seconds"], rows["a"]["max_seconds"]) == (2, 15.0, 20.0)
    assert rows["b"]["failures"] == ["reply lacks 'z'"] and rows["c"]["median_seconds"] is None
    assert s["tags"]["nfr01"] == {"scenarios": 2, "all_runs_pass": 1, "runs": 4, "runs_passed": 3}
    assert (s["runs"], s["runs_passed"], s["median_seconds"], s["max_seconds"]) == (5, 3, 25.0, 40.0)


def test_select_by_id_and_tag():
    chosen = [scenario("keydates_a", tags=["keydates"]), scenario("fees_a", tags=["fees"]), scenario("q1", tags=["nfr01"])]
    assert [s.id for s in scenarios.select(chosen, ["keydates"], [])] == ["keydates_a"]
    assert [s.id for s in scenarios.select(chosen, [], ["nfr01", "fees"])] == ["fees_a", "q1"]
    with pytest.raises(ScenarioError):
        scenarios.select(chosen, ["nothing"], [])


# The command line

def good_client(number):
    return FakeClient(number, lambda n, p: reply("Hello Sam", calls("get_student_profile"), 3.0))


def test_main_passes_writes_a_report_and_exits_zero(tmp_path, capsys):
    report = tmp_path / "out" / "report.json"
    assert scenarios.main(["--only", "greeting_first", "--report", str(report)], make_client=good_client) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["runs_passed"] == 1 and data["results"][0]["scenario"] == "greeting_first_message"
    assert data["results"][0]["replies"] == ["Hello Sam"]
    assert "PASS" in capsys.readouterr().out


def test_main_exits_one_when_a_run_fails(tmp_path, capsys):
    bad = lambda number: FakeClient(number, lambda n, p: reply("Welcome", calls("get_fees")))
    assert scenarios.main(["--only", "greeting_first", "--no-report", "--repeat", "2"], make_client=bad) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "0/2" in out


def test_main_list_and_no_match(capsys):
    assert scenarios.main(["--list", "--tag", "nfr01"]) == 0
    listed = capsys.readouterr().out
    assert listed.count("nfr01") == 10 and "q01_program_structure" in listed
    assert scenarios.main(["--only", "no such scenario"]) == 2


def test_main_does_not_write_a_report_with_no_report(tmp_path, monkeypatch):
    monkeypatch.setattr(scenarios, "REPORT_DIR", tmp_path / "reports")
    scenarios.main(["--only", "greeting_first", "--no-report"], make_client=good_client)
    assert not (tmp_path / "reports").exists()
    scenarios.main(["--only", "greeting_first"], make_client=good_client)
    assert len(list((tmp_path / "reports").glob("*.json"))) == 1


# Platform errors are retried and reported, not counted as wrong answers

def flaky(errors, then="Hello Sam"):
    """A client whose first replies are platform errors."""
    state = {"asked": 0}

    def script(number, prompt):
        state["asked"] += 1
        return reply(errors[state["asked"] - 1] if state["asked"] <= len(errors) else then)
    return FakeClient("S0000001", script), state


def test_a_platform_error_is_asked_again_and_the_retry_is_recorded():
    client, state = flaky(["I have encountered an error. Please try again."])
    r = run_scenario(scenario(), 1, lambda n: client, retries=1)
    assert r.passed and r.retries == 1 and state["asked"] == 2 and r.replies == ["Hello Sam"]


def test_a_persistent_platform_error_fails_with_its_own_message():
    client, state = flaky(["the tool is temporarily unavailable"] * 3)
    r = run_scenario(scenario(), 1, lambda n: client, retries=1)
    assert not r.passed and r.retries == 1 and state["asked"] == 2
    assert r.failures[0].startswith("platform error: the tool is temporarily unavailable")


def test_no_retries_when_told_not_to():
    client, state = flaky(["I have encountered an error."])
    r = run_scenario(scenario(), 1, lambda n: client, retries=0)
    assert not r.passed and r.retries == 0 and state["asked"] == 1


def test_a_failed_run_from_the_platform_is_also_retried():
    from planner.client import ChatError
    state = {"asked": 0}

    def script(number, prompt):
        state["asked"] += 1
        if state["asked"] == 1:
            raise ChatError("The run failed: boom")
        return reply("Hello Sam")
    r = run_scenario(scenario(), 1, lambda n: FakeClient("S0000001", script), retries=1)
    assert r.passed and r.retries == 1
    state["asked"] = -5  # never succeeds within the retries
    r = run_scenario(scenario(), 1, lambda n: FakeClient("S0000001", lambda n_, p: (_ for _ in ()).throw(ChatError("down"))), retries=1)
    assert not r.passed and "ChatError" in r.failures[0]


def test_a_wrong_answer_is_not_retried():
    client, state = flaky([], then="Welcome")
    r = run_scenario(scenario(), 1, lambda n: client, retries=3)
    assert not r.passed and r.retries == 0 and state["asked"] == 1


def test_the_summary_and_command_report_retried_runs(capsys):
    client_factory = lambda number: flaky(["I have encountered an error."], then="Hello Sam")[0]
    assert scenarios.main(["--only", "greeting_first", "--no-report", "--retries", "1"], make_client=client_factory) == 0
    out = capsys.readouterr().out
    assert "(retried 1x)" in out and "1 run(s) were retried" in out
    results = [RunResult("a", 1, True, retries=1), RunResult("a", 2, True)]
    assert summarise([scenario("a")], results)["retried_runs"] == 1


# Running against the mock service

def test_skip_tag_leaves_scenarios_out():
    chosen = [scenario("a", tags=["enrol"]), scenario("b", tags=["service"]), scenario("c", tags=["service", "enrol"])]
    assert [s.id for s in scenarios.select(chosen, [], [], ["service"])] == ["a"]
    assert [s.id for s in scenarios.select(chosen, [], ["enrol"], ["service"])] == ["a"]
    with pytest.raises(ScenarioError):
        scenarios.select(chosen, [], [], ["service", "enrol"])


def test_stateful_scenarios_run_one_at_a_time_after_the_rest_with_a_reset_around_each_run():
    log, lock = [], __import__("threading").Lock()

    def make(number):
        def answer(n, prompt):
            with lock:
                log.append("ask")
            return reply("hello", calls("get_student_profile"), 1.0)
        return FakeClient(number, answer)
    chosen = [scenario("plain_a"), scenario("changes", tags=["stateful"]), scenario("plain_b")]
    on_result = lambda r: log.append(f"done {r.scenario} {r.run}")
    results = run_all(chosen, repeat=2, workers=3, make_client=make, on_result=on_result, reset=lambda: log.append("reset"))
    assert [(r.scenario, r.run) for r in results] == [("plain_a", 1), ("plain_a", 2), ("changes", 1), ("changes", 2), ("plain_b", 1), ("plain_b", 2)]
    assert log[0] == "reset"
    assert [x for x in log if x.startswith("done changes") or x == "reset"] == [
        "reset", "reset", "done changes 1", "reset", "reset", "done changes 2", "reset"]
    assert log.index("done plain_a 2") < log.index("done changes 1") and log.index("done plain_b 2") < log.index("done changes 1")


def test_without_a_reset_stateful_scenarios_run_like_any_other():
    log = []
    make = lambda number: FakeClient(number, lambda n, p: reply("hello", calls("get_student_profile"), 1.0))
    results = run_all([scenario("changes", tags=["stateful"])], repeat=2, workers=2, make_client=make, on_result=log.append)
    assert len(results) == 2 and all(r.passed for r in results)


def test_the_resetter_posts_to_the_deployed_services_admin_reset(tmp_path):
    config = tmp_path / "service_config.json"
    config.write_text(json.dumps({"url": "https://x.trycloudflare.com/", "key": "k"}))
    seen = []

    class Ok:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(request, timeout=None):
        seen.append((request.get_method(), request.full_url, request.get_header("X-api-key")))
        return Ok()
    scenarios.service_resetter(config, opener)()
    assert seen == [("POST", "https://x.trycloudflare.com/admin/reset", "k")]


def test_the_resetter_explains_a_missing_config_and_an_unreachable_service(tmp_path):
    with pytest.raises(ScenarioError, match="mockapi"):
        scenarios.service_resetter(tmp_path / "missing.json")
    config = tmp_path / "service_config.json"
    config.write_text(json.dumps({"url": "https://x.com", "key": "k"}))

    def down(request, timeout=None):
        raise scenarios.urllib.error.URLError("refused")
    with pytest.raises(ScenarioError, match="could not be reached"):
        scenarios.service_resetter(config, down)()


def test_main_stops_with_a_message_when_there_is_no_service_to_reset(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(scenarios, "SERVICE_CONFIG", tmp_path / "missing.json")
    assert scenarios.main(["--only", "greeting_first", "--reset-service", "--no-report"], make_client=good_client) == 2
    assert "mockapi" in capsys.readouterr().out
    monkeypatch.setattr(scenarios, "SERVICE_CONFIG", tmp_path / "missing.json")
    assert scenarios.main(["--only", "greeting_first", "--no-report"], make_client=good_client) == 0  # not asked to reset
