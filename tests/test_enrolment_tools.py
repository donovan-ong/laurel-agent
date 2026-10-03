import json
import re
import shutil

import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import common, enrolment as enr, scheduling as sch
from tools.common import load
from tools.enrolment_tools import check_enrolment, list_enrolments, submit_enrolment

WORK = {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def pick(course, term, component, day=None, start=None, index=0):
    options = sch.components(sch.get_offering(course, term))[component]
    if day:
        options = [o for o in options if (o["day"], o["start"]) == (day, start)]
    return options[index]["class_id"]


def classes(course, term, day="Mon", start="18:00"):
    return [pick(course, term, "lecture"), pick(course, term, "workshop", day, start)]


def check(number, ids, availability=None):
    return check_enrolment.fn(context=ctx(number), class_ids=ids, availability=availability)


def codes(result):
    return [r["code"] for r in result["reasons"]]


def submit(number, ids, confirmed=True, availability=None, check_id=None):
    return submit_enrolment.fn(context=ctx(number), class_ids=ids, student_confirmed=confirmed, availability=availability,
                               check_id=check_id if check_id is not None else enr.check_id(load("students.json")[int(number[-1]) - 1]["student_number"], ids))


def edit_timetable(folder, change):
    path = folder / "timetable.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


# The happy path

def test_an_eligible_check_returns_a_summary_and_a_check_id():
    ids = classes("COSC2148", "2027-S1")
    r = check("S0000001", ids)
    assert r["found"] and r["eligible"] is True and r["reasons"] == []
    s = r["summary"]
    assert (s["course_id"], s["term"], s["lecture"]["class_id"], s["workshop"]["when"]) == ("COSC2148", "2027-S1", "1015", "Monday 18:00 to 20:00")
    assert re.fullmatch(r"[0-9a-f]{16}", r["check_id"]) and "SIMULATION" in r["simulation_notice"]


def test_submitting_after_a_check_enrols_with_a_reference_and_the_notice():
    ids = classes("COSC2148", "2027-S1")
    r = check("S0000001", ids)
    s = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=r["check_id"], student_confirmed=True)
    assert s["status"] == "enrolled" and re.fullmatch(r"SIM-\d{6}", s["reference"]) and s["simulated"] is True
    assert "SIMULATION" in s["notice"] and "synthetic" in s["notice"]
    assert s["enrolment"] == r["summary"]


def test_nothing_is_stored_so_the_same_request_gives_the_same_answer():
    ids = classes("COSC2148", "2027-S1")
    first, again = check("S0000001", ids), check("S0000001", ids)
    assert first == again
    one = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=first["check_id"], student_confirmed=True)
    two = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=first["check_id"], student_confirmed=True)
    assert one == two


def test_the_check_id_depends_on_the_student_and_the_classes_but_not_their_order():
    ids = classes("COSC2148", "2027-S1")
    assert enr.check_id("S0000001", ids) == enr.check_id("S0000001", list(reversed(ids)))
    assert enr.check_id("S0000001", ids) != enr.check_id("S0000002", ids)
    assert enr.check_id("S0000001", ids) != enr.check_id("S0000001", classes("COSC2148", "2027-S1", "Wed", "18:00"))
    assert enr.reference("S0000001", ids) != enr.reference("S0000002", ids)


def test_class_numbers_given_as_numbers_are_accepted():
    ids = [int(i) for i in classes("COSC2148", "2027-S1")]
    assert check("S0000001", ids)["eligible"] is True


# Submit refuses

def test_submit_needs_an_explicit_true_confirmation():
    ids = classes("COSC2148", "2027-S1")
    for value in (False, None, "yes", 1, "true"):
        r = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=enr.check_id("S0000001", ids), student_confirmed=value)
        assert r["status"] == "refused" and r["error"]["code"] == "NOT_CONFIRMED" and r["simulated"] is True and "SIMULATION" in r["notice"]


def test_submit_needs_the_check_id_for_these_classes():
    ids, other = classes("COSC2148", "2027-S1"), classes("COSC2148", "2027-S1", "Wed", "18:00")
    for bad in ("", "abc", enr.check_id("S0000001", other), enr.check_id("S0000002", ids)):
        r = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=bad, student_confirmed=True)
        assert r["error"]["code"] == "INVALID_CHECK" and "SIMULATION" in r["notice"]


def test_submit_checks_again_and_reports_the_first_problem_with_all_of_them():
    ids = classes("COSC2148", "2027-S1", "Mon", "10:00")  # a daytime workshop
    r = submit_enrolment.fn(context=ctx("S0000001"), class_ids=ids, check_id=enr.check_id("S0000001", ids),
                            student_confirmed=True, availability=WORK)
    assert r["status"] == "refused" and r["error"]["code"] == "TIMETABLE_CLASH" and "SIMULATION" in r["notice"]
    assert [x["code"] for x in r["all_reasons"]] == ["TIMETABLE_CLASH"]


def test_nothing_works_without_a_login():
    ids = classes("COSC2148", "2027-S1")
    for r in (check_enrolment.fn(context=AgentRun(), class_ids=ids), list_enrolments.fn(context=AgentRun()),
              submit_enrolment.fn(context=AgentRun(), class_ids=ids, check_id="x", student_confirmed=True)):
        assert r["found"] is False and "Nobody is logged in" in r["reason"]


# Invalid selections

@pytest.mark.parametrize("ids,message", [
    ([], "exactly two"), (None, "exactly two"), (["1015"], "exactly two"), (["1015", "1015"], "exactly two"),
    (["1015", "1102", "1103"], "exactly two"), (["1015", "9999"], "There is no class 9999"),
])
def test_wrong_numbers_of_classes_are_an_invalid_selection(ids, message):
    r = check("S0000001", ids)
    assert r["eligible"] is False and codes(r) == ["INVALID_SELECTION"] and message in r["reasons"][0]["message"] and r["summary"] is None


def test_two_lectures_two_workshops_or_mixed_courses_are_invalid():
    lectures = [o["class_id"] for o in sch.components(sch.get_offering("COSC2148", "2027-S1"))["lecture"]]
    workshops = [o["class_id"] for o in sch.components(sch.get_offering("COSC2148", "2027-S1"))["workshop"]][:2]
    assert "not lecture and lecture" in check("S0000001", lectures)["reasons"][0]["message"]
    assert "not workshop and workshop" in check("S0000001", workshops)["reasons"][0]["message"]
    other_course = classes("COSC2462", "2027-S1", "Tue", "18:00")
    assert "same course and term" in check("S0000001", [lectures[0], other_course[1]])["reasons"][0]["message"]
    other_term = classes("COSC2148", "2027-S2")
    assert "same course and term" in check("S0000001", [lectures[0], other_term[1]])["reasons"][0]["message"]


# Reasons

def test_a_full_lecture_and_a_closed_workshop_are_reported_with_codes():
    ids = classes("COSC2148", "2027-S2")
    r = check("S0000001", ids)
    assert r["eligible"] is False and codes(r) == ["ENROLMENT_CLOSED", "CLASS_FULL"]
    assert "is full (60 of 60 seats taken)" in r["reasons"][1]["message"] and r["reasons"][1]["alternatives"] == []


def test_a_class_in_the_current_term_is_closed():
    ids = classes("COSC2110", "2026-S2")
    r = check("S0000001", ids)
    assert codes(r) == ["ENROLMENT_CLOSED", "ENROLMENT_CLOSED"] and r["eligible"] is False


def test_alternatives_list_the_other_open_classes(data_copy):
    def fill(data):
        offering = next(o for o in data if (o["course_id"], o["term"]) == ("COSC2148", "2027-S1"))
        target = next(o for c in offering["components"] if c["component"] == "workshop" for o in c["options"] if (o["day"], o["start"]) == ("Mon", "18:00"))
        target["seats_taken"] = target["seats_total"]
    edit_timetable(data_copy, fill)
    r = check("S0000001", classes("COSC2148", "2027-S1"))
    assert codes(r) == ["CLASS_FULL"]
    alts = r["reasons"][0]["alternatives"]
    assert alts and all(a["seats_left"] > 0 and a["enrolment_open"] for a in alts) and len(alts) <= 5
    assert all(a["class_id"] != pick("COSC2148", "2027-S1", "workshop", "Mon", "18:00") for a in alts)


def test_missing_prerequisites_are_named():
    r = check("S0000001", classes("COSC3154", "2027-S1", None, None))
    assert codes(r) == ["PREREQUISITE_NOT_MET"]
    assert "Computing Research and Project Preparation (COSC2148)" in r["reasons"][0]["message"]
    assert "Preliminary Computer Science Honours Thesis (COSC2462)" in r["reasons"][0]["message"]


def test_a_student_who_has_passed_the_prerequisites_can_enrol_and_the_unconfirmed_workshop_is_noted():
    r = check("S0000004", classes("COSC3154", "2027-S1", None, None), WORK)
    assert r["eligible"] is True and any("not confirmed" in n for n in r["notes"])


def test_already_enrolled_and_already_passed():
    assert codes(check("S0000008", classes("COSC2148", "2027-S1"))) == ["ALREADY_ENROLLED"]
    assert codes(check("S0000004", classes("COSC2148", "2027-S1"))) == ["ALREADY_PASSED"]


def test_a_failed_course_can_be_taken_again():
    assert check("S0000005", classes("COSC2462", "2027-S1", "Tue", "18:00"))["eligible"] is True


def test_an_account_hold_blocks_enrolment():
    ids = classes("COSC3154", "2027-S1", None, None)
    r = check("S0000007", ids)
    assert codes(r) == ["ACCOUNT_HOLD"] and "3600 AUD" in r["reasons"][0]["message"]
    s = submit("S0000007", ids)
    assert s["status"] == "refused" and s["error"]["code"] == "ACCOUNT_HOLD"


def test_a_workshop_that_clashes_with_availability_is_refused_but_an_evening_one_is_not():
    assert codes(check("S0000001", classes("COSC2148", "2027-S1", "Mon", "10:00"), WORK)) == ["TIMETABLE_CLASH"]
    assert check("S0000001", classes("COSC2148", "2027-S1", "Mon", "18:00"), WORK)["eligible"] is True
    assert check("S0000001", classes("COSC2148", "2027-S1", "Mon", "10:00"))["eligible"] is True  # no availability given


def test_a_workshop_that_overlaps_an_existing_enrolment_clashes():
    # S0000008 is enrolled for 2027-S1 in COSC2148 (Mon 18:00) and COSC2462 (Tue 18:00)
    r = check("S0000008", classes("COSC1183", "2027-S1", "Mon", "18:00"))
    assert codes(r) == ["TIMETABLE_CLASH"] and "Computing Research and Project Preparation" in r["reasons"][0]["message"]
    assert check("S0000008", classes("COSC2632", "2027-S1", "Wed", "18:00"))["eligible"] is True


def test_reasons_come_in_priority_order():
    ids = classes("COSC2148", "2027-S2", "Mon", "18:00")
    r = check("S0000007", ids)
    assert codes(r) == [c for c in enr.PRIORITY if c in codes(r)] and codes(r)[0] == "ENROLMENT_CLOSED"


def test_bad_availability_is_explained():
    r = check("S0000001", classes("COSC2148", "2027-S1"), {"busy": [{"days": ["Mon"], "start": "x", "end": "y"}]})
    assert r["found"] is False and "not a time" in r["reason"]


# List

def test_list_enrolments_shows_the_record_with_times():
    r = list_enrolments.fn(context=ctx("S0000004"))
    assert [e["title"] for e in r["enrolments"]] == ["Data Mining", "Machine Learning"]
    assert all(e["status"] == "enrolled, this term" and e["lecture"]["when"] and e["workshop"]["when"] for e in r["enrolments"])
    assert "not included" in r["note"] and "SIMULATION" in r["simulation_notice"]


def test_list_enrolments_marks_future_terms_and_shows_nothing_for_a_new_student():
    future = list_enrolments.fn(context=ctx("S0000008"))["enrolments"]
    assert {e["status"] for e in future} == {"enrolled, future term"} and future[0]["term"] == "2027-S1"
    assert list_enrolments.fn(context=ctx("S0000001"))["enrolments"] == []


def test_list_enrolments_never_shows_another_student():
    text = json.dumps(list_enrolments.fn(context=ctx("S0000001")))
    assert "Data Mining" not in text and "S0000004" not in text


# Tool definitions

def test_only_submit_is_a_write_tool_and_none_takes_a_student():
    assert submit_enrolment.__tool_spec__.permission.value == "read_write"
    assert check_enrolment.__tool_spec__.permission.value == list_enrolments.__tool_spec__.permission.value == "read_only"
    for t in (check_enrolment, submit_enrolment, list_enrolments):
        props = set(t.__tool_spec__.input_schema.properties)
        assert not props & {"student_number", "student_id", "student"}
    assert {"class_ids", "check_id", "student_confirmed"} <= set(submit_enrolment.__tool_spec__.input_schema.properties)
    assert "Never call submit_enrolment in the same reply" in check_enrolment.__tool_spec__.description
    assert "clearly said yes" in submit_enrolment.__tool_spec__.description
