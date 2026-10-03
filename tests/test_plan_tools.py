import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import planning, scheduling as sch
from tools.common import load
from tools.plan_tools import build_plan

WORK = {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}
NO_TUESDAYS = {"busy": [{"days": ["Tue"], "start": "00:00", "end": "23:59"}]}
STUDENTS = {s["student_number"]: s for s in load("students.json")}
OPTIONS = set(load("programs.json")[0]["option_list"]["course_ids"])


def plan_for(number, availability=None, **kwargs):
    r = build_plan.fn(context=AgentRun(request_context={"student_number": number}), availability=availability, **kwargs)
    assert r["found"], r
    return r["plan"]


def terms_of(plan):
    return {c["course_id"]: s["term"] for s in plan["semesters"] for c in s["courses"]}


def rows(plan):
    return [c for s in plan["semesters"] for c in s["courses"]]


def test_a_part_time_worker_finishes_in_four_semesters_matching_the_published_two_years():
    p = plan_for("S0000001", WORK)
    assert (p["semesters_needed"], p["years"], p["credit_points_per_semester"], p["load"], p["complete"]) == (4, 2.0, 24, "part-time", True)
    assert [s["term"] for s in p["semesters"]] == ["2027-S1", "2027-S2", "2028-S1", "2028-S2"]
    assert [s["credit_points"] for s in p["semesters"]] == [24, 24, 24, 24] and p["credit_points_planned"] == 96
    assert "matches the published part-time duration of 2" in p["published_duration_note"]


def test_the_compulsory_stage_a_courses_come_first_then_options_then_the_thesis():
    p = plan_for("S0000001", WORK)
    assert [c["course_id"] for c in p["semesters"][0]["courses"]] == ["COSC2148", "COSC2462"]
    assert [c["kind"] for c in p["semesters"][1]["courses"]] == ["option", "option"]
    third = [c["course_id"] for c in p["semesters"][2]["courses"]]
    assert third[0] == "COSC3154" and third[1] in OPTIONS
    assert [c["course_id"] for c in p["semesters"][3]["courses"]] == ["COSC3155"]


def test_every_planned_workshop_fits_the_availability_and_none_overlap():
    p = plan_for("S0000001", WORK)
    blocks = sch.parse_availability(WORK)
    for s in p["semesters"]:
        timed = []
        for c in s["courses"]:
            offering = sch.get_offering(c["course_id"], s["term"])
            w = next(o for o in sch.components(offering)["workshop"] if o["class_id"] == c["workshop"]["class_id"])
            assert sch.fit(w, blocks) in ("fits", "unknown") and sch.is_available(w)
            if w["day"]:
                assert not any(sch.overlaps(w["day"], w["start"], w["end"], [t]) for t in timed)
                timed.append((w["day"], w["start"], w["end"]))


def test_prerequisites_and_part_order_are_respected_in_every_plan():
    for number, availability in [("S0000001", WORK), ("S0000002", NO_TUESDAYS), ("S0000003", None)]:
        p = plan_for(number, availability)
        t = terms_of(p)
        assert t["COSC3154"] > t["COSC2148"] and t["COSC3154"] > t["COSC2462"]
        assert t["COSC3155"] >= t["COSC3154"] and t["COSC2462"] >= t["COSC2148"]


def test_thesis_workshops_are_flagged_unconfirmed_and_options_are_marked_suggested():
    p = plan_for("S0000001", WORK)
    assert p["unconfirmed_workshops"] == ["COSC3154", "COSC3155"]
    assert all(c["workshop_unconfirmed"] == (c["course_id"] in ("COSC3154", "COSC3155")) for c in rows(p))
    assert len(p["suggested_options"]) == 3 and set(p["suggested_options"]) <= OPTIONS
    assert all(c["suggested_option"] for c in rows(p) if c["kind"] == "option")
    assert any("suggested" in a for a in build_plan.fn(context=AgentRun(request_context={"student_number": "S0000001"}), availability=WORK)["plan"]["assumptions"])


def test_a_full_time_student_who_avoids_tuesdays_finishes_in_two_semesters_with_no_tuesday_workshop():
    p = plan_for("S0000002", NO_TUESDAYS)
    assert (p["semesters_needed"], p["credit_points_per_semester"], p["load"]) == (2, 48, "full-time")
    assert [s["credit_points"] for s in p["semesters"]] == [48, 48]
    assert all("Tuesday" not in c["workshop"]["when"] for c in rows(p))
    assert "matches the published full-time duration of 1" in p["published_duration_note"]


def test_the_load_can_be_changed_and_the_plan_is_rebuilt():
    faster = plan_for("S0000001", None, credit_points_per_semester=48)
    assert faster["semesters_needed"] == 2 and faster["load"] == "full-time"
    slower = plan_for("S0000002", None, credit_points_per_semester=24)
    assert slower["semesters_needed"] == 4 and slower["load"] == "part-time"


def test_a_course_bigger_than_the_semester_limit_is_reported_not_forced():
    p = plan_for("S0000001", None, credit_points_per_semester=12)
    assert p["complete"] is False
    thesis_b = next(u for u in p["unplaced"] if u["course_id"] == "COSC3155")
    assert "needs 24 credit points, more than the 12 allowed" in thesis_b["reason"]
    assert all(s["credit_points"] <= 12 for s in p["semesters"]) and p["published_duration_note"] is None


def test_a_student_partway_through_only_gets_the_rest():
    p = plan_for("S0000004", WORK)
    # Full-time this semester (Data Mining, Machine Learning, Cloud Security and Thesis Part A): only Part B is left
    assert p["already_passed"] == ["COSC2148", "COSC2462"]
    assert p["in_progress_assumed_passed"] == ["COSC2110", "COSC2673", "COSC3154", "INTE2402"]
    assert p["start_term"] == "2027-S1" and p["semesters_needed"] == 1 and p["suggested_options"] == []
    assert [c["course_id"] for c in p["semesters"][0]["courses"]] == ["COSC3155"]
    assert p["published_duration_note"] is None
    assert any("assumed to be passed" in a for a in build_plan.fn(context=AgentRun(request_context={"student_number": "S0000004"}))["plan"]["assumptions"])


def test_a_student_in_their_final_semester_has_nothing_left_to_plan():
    p = plan_for("S0000006", WORK)
    assert p["semesters"] == [] and p["semesters_needed"] == 0 and p["complete"] is True and p["credit_points_planned"] == 0


def test_enrolments_already_made_for_a_future_term_are_kept():
    p = plan_for("S0000008", WORK)
    first = p["semesters"][0]["courses"]
    assert [(c["course_id"], c["status"]) for c in first] == [("COSC2148", "already enrolled"), ("COSC2462", "already enrolled")]
    enrolled = {e["course_id"]: e for e in STUDENTS["S0000008"]["current_enrolments"]}
    workshop_ids = {c["course_id"]: c["workshop"]["class_id"] for c in first}
    assert all(workshop_ids[cid] in e["class_ids"] for cid, e in enrolled.items())
    assert p["semesters_needed"] == 4


def test_preferred_options_are_used_when_they_can_be_placed():
    p = plan_for("S0000001", WORK, preferred_option_ids=["COSC2673", "Cloud Security"])
    picked = [c["course_id"] for c in rows(p) if c["kind"] == "option"]
    assert picked[:2] == ["COSC2673", "INTE2402"]
    assert [c["suggested_option"] for c in rows(p) if c["kind"] == "option"] == [False, False, True]


def test_a_preferred_option_that_cannot_fit_is_reported_and_replaced():
    p = plan_for("S0000001", WORK, preferred_option_ids=["Programming Autonomous Robots"])
    assert p["unplaced"][0]["course_id"] == "COSC2814" and p["unplaced"][0]["your_choice"] is True
    assert "every workshop clashes" in p["unplaced"][0]["reason"] and p["complete"] is False
    assert len([c for c in rows(p) if c["kind"] == "option"]) == 3


def test_a_compulsory_course_that_never_fits_blocks_the_ones_that_need_it():
    everything = {"busy": [{"days": sch.DAY_ABBREVIATIONS, "start": "00:00", "end": "23:59"}]}
    p = plan_for("S0000001", everything)
    assert p["complete"] is False and p["semesters"] == []
    assert {u["course_id"] for u in p["unplaced"]} >= {"COSC2148", "COSC2462", "COSC3154", "COSC3155"}
    assert "every workshop clashes" in next(u for u in p["unplaced"] if u["course_id"] == "COSC2148")["reason"]


def test_the_plan_starts_at_the_first_open_term_and_says_so():
    p = plan_for("S0000001", None, start_term="2026-S2")
    assert p["start_term"] == "2027-S1" and "not open for enrolment" in p["start_term_note"]
    later = plan_for("S0000001", None, start_term="2027-S2")
    assert later["start_term"] == "2027-S2" and later["start_term_note"] is None
    # COSC2148's only lecture is full in 2027-S2, so it slips to the next term it runs
    assert later["semesters"][0]["semester_number"] == 1 and later["complete"] is True
    assert terms_of(later)["COSC2148"] == "2028-S1"


def test_a_plan_that_runs_off_the_end_of_the_timetable_says_so():
    p = plan_for("S0000001", None, start_term="2032-S1")  # the last term with room for the whole plan
    assert p["complete"] is False
    assert any("timetable" in u["reason"] or "no term" in u["reason"] for u in p["unplaced"])


def test_the_same_inputs_give_the_same_plan():
    a = build_plan.fn(context=AgentRun(request_context={"student_number": "S0000001"}), availability=WORK)
    b = build_plan.fn(context=AgentRun(request_context={"student_number": "S0000001"}), availability=WORK)
    assert a == b


def test_total_credit_points_add_up_for_a_complete_plan():
    for number, availability in [("S0000001", WORK), ("S0000002", NO_TUESDAYS)]:
        p = plan_for(number, availability)
        assert p["credit_points_planned"] == sum(c["credit_points"] for c in rows(p)) == 96
        assert len({c["course_id"] for c in rows(p)}) == len(rows(p))


def test_bad_inputs_and_no_login_are_explained():
    ctx = AgentRun(request_context={"student_number": "S0000001"})
    assert build_plan.fn(context=AgentRun())["found"] is False
    assert "not one option course" in build_plan.fn(context=ctx, preferred_option_ids=["COSC2148"])["reason"]
    assert "not one option course" in build_plan.fn(context=ctx, preferred_option_ids=["thesis"])["reason"]
    assert "at least 12" in build_plan.fn(context=ctx, credit_points_per_semester=6)["reason"]
    assert "no timetable" in build_plan.fn(context=ctx, start_term="2099-S1")["reason"].lower()
    assert "availability must look like" in build_plan.fn(context=ctx, availability="9 to 5")["reason"]


def test_availability_used_is_echoed_and_the_tool_takes_no_student():
    r = build_plan.fn(context=AgentRun(request_context={"student_number": "S0000001"}), availability=WORK)
    assert r["plan"]["availability_used"][0] == "Mon 09:00 to 17:00" and len(r["plan"]["availability_used"]) == 5
    assert build_plan.fn(context=AgentRun(request_context={"student_number": "S0000001"}))["plan"]["availability_used"].startswith("none given")
    props = set(build_plan.__tool_spec__.input_schema.properties)
    assert not props & {"student_number", "student_id"} and build_plan.__tool_spec__.permission.value == "read_only"
    assert r["source"]["file"].startswith("programs.json, courses.json, timetable.json")


def test_load_labels():
    program = load("programs.json")[0]
    assert planning.load_label(24, program) == "part-time" and planning.load_label(48, program) == "full-time"
    assert planning.load_label(36, program) is None
