import re
from datetime import date

import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import dropping as drop, enrolment as enr, scheduling as sch
from tools.common import load
from tools.enrolment_tools import check_drop, drop_enrolment

STUDENTS = {s["student_number"]: s for s in load("students.json")}


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def assess(number, course, term, today, **kw):
    return drop.assess(STUDENTS[number], course, term, today=today, **kw)


# The rules, by date. Robin (S0000008) is enrolled in COSC2148 in 2027-S1 (census 9 April 2027, no published drop deadline).
# Casey Delacroix's 2026-S2 enrolments (S0000004) have census 31 August 2026 and a published drop deadline of 18 September 2026.

def test_before_the_census_date_the_fee_is_avoided_with_no_penalty():
    r = assess("S0000008", "COSC2148", "2027-S1", date(2027, 4, 8))
    c = r["consequences"]
    assert r["can_drop"] is True and r["reasons"] == []
    assert (c["phase"], c["fee_outcome"], c["academic_penalty"]) == ("before_census", "avoided", False)
    assert "not charged" in c["message"] and "Friday 9 April 2027" in c["message"]


def test_on_the_census_date_itself_the_fee_still_applies():
    c = assess("S0000008", "COSC2148", "2027-S1", date(2027, 4, 9))["consequences"]
    assert c["phase"] == "deadline_not_published" and c["fee_outcome"] == "still_payable"


def test_after_census_and_on_or_before_the_deadline_the_fee_applies_without_penalty():
    for day in (date(2026, 9, 1), date(2026, 9, 18)):
        r = assess("S0000004", "COSC2110", "2026-S2", day)
        c = r["consequences"]
        assert r["can_drop"] is True
        assert (c["phase"], c["fee_outcome"], c["academic_penalty"]) == ("after_census", "still_payable", False)
        assert "still applies" in c["message"] and "Friday 18 September 2026" in c["message"]


def test_after_the_deadline_the_drop_is_refused_naming_the_date():
    r = assess("S0000004", "COSC2110", "2026-S2", date(2026, 9, 19))
    assert r["can_drop"] is False and r["consequences"]["phase"] == "after_deadline"
    assert [x["code"] for x in r["reasons"]] == ["DROP_DEADLINE_PASSED"]
    assert "Friday 18 September 2026" in r["reasons"][0]["message"] and "Student Connect" in r["reasons"][0]["message"]


def test_a_term_with_no_published_deadline_is_allowed_after_census_with_a_warning():
    r = assess("S0000008", "COSC2148", "2027-S1", date(2027, 5, 1))
    c = r["consequences"]
    assert r["can_drop"] is True and c["drop_deadline"] is None and c["academic_penalty"] is None
    assert "not in this demo's data" in c["message"]


def test_a_term_that_has_ended_cannot_be_dropped():
    r = assess("S0000004", "COSC2110", "2026-S2", date(2026, 12, 1))
    assert r["can_drop"] is False and r["consequences"]["phase"] == "term_ended"
    assert r["reasons"][0]["code"] == "DROP_DEADLINE_PASSED" and "ended" in r["reasons"][0]["message"]


def test_not_enrolled_is_a_coded_refusal_with_nothing_to_summarise():
    r = assess("S0000001", "COSC2148", "2027-S1", date(2026, 9, 22))
    assert r["can_drop"] is False and r["summary"] is None and r["consequences"] is None
    assert r["reasons"][0]["code"] == "NOT_ENROLLED"


def test_the_right_term_matters():
    assert assess("S0000008", "COSC2148", "2027-S2", date(2026, 9, 22))["reasons"][0]["code"] == "NOT_ENROLLED"


@pytest.mark.parametrize("fee_type,amount", [("hecs_csp", "1,800"), ("domestic_full_fee", "3,600"), ("international", "5,400")])
def test_the_fee_is_at_the_students_rate_per_12_credit_points(fee_type, amount):
    student = {**STUDENTS["S0000008"], "fee_type": fee_type}
    r = drop.assess(student, "COSC2148", "2027-S1", today=date(2027, 1, 4))
    assert r["consequences"]["course_fee"] == float(amount.replace(",", "")) * r["summary"]["credit_points"] / 12
    if r["summary"]["credit_points"] == 12:
        assert amount in r["consequences"]["message"]
    assert r["consequences"]["withdrawal_rule"] == load("fees.json")["fee_types"][fee_type]["withdrawal_rule"]


def test_the_summary_names_the_course_and_the_students_classes():
    s = assess("S0000008", "COSC2148", "2027-S1", date(2027, 1, 4))["summary"]
    assert (s["course_id"], s["term"], s["lecture"]["class_id"], s["workshop"]["class_id"]) == ("COSC2148", "2027-S1", "1015", "1102")
    assert s["title"] and s["workshop"]["when"]


def test_enrolments_can_be_supplied_by_the_service():
    student = STUDENTS["S0000001"]
    made = [{"course_id": "COSC2148", "term": "2027-S1", "class_ids": ["1015", "1102"]}]
    assert assess("S0000001", "COSC2148", "2027-S1", date(2027, 1, 4), enrolments=made)["can_drop"] is True
    assert assess("S0000008", "COSC2148", "2027-S1", date(2027, 1, 4), enrolments=[])["reasons"][0]["code"] == "NOT_ENROLLED"


# The tools

def call_check(number, course, term):
    return check_drop.fn(context=ctx(number), course_id=course, term=term)


def test_check_drop_returns_a_check_id_a_notice_and_a_source(monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: date(2026, 9, 22))
    r = call_check("S0000008", "COSC2148", "2027-S1")
    assert r["found"] and r["can_drop"] is True
    assert re.fullmatch(r"[0-9a-f]{16}", r["check_id"]) and "SIMULATION" in r["simulation_notice"]
    assert r["source"]["file"] == "terms.json"
    assert r["check_id"] == drop.check_id("S0000008", "COSC2148", "2027-S1")


def test_the_demo_students_on_22_september_2026(monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: date(2026, 9, 22))
    assert call_check("S0000008", "COSC2148", "2027-S1")["consequences"]["fee_outcome"] == "avoided"
    for number, course in (("S0000004", "COSC2110"), ("S0000005", "COSC2462"), ("S0000007", "INTE2402")):
        r = call_check(number, course, "2026-S2")
        assert r["can_drop"] is False and r["reasons"][0]["code"] == "DROP_DEADLINE_PASSED"


def test_the_check_id_depends_on_student_course_and_term():
    a = drop.check_id("S0000008", "COSC2148", "2027-S1")
    assert a != drop.check_id("S0000001", "COSC2148", "2027-S1")
    assert a != drop.check_id("S0000008", "COSC2462", "2027-S1")
    assert a != drop.check_id("S0000008", "COSC2148", "2027-S2")
    assert a != enr.check_id("S0000008", ["COSC2148", "2027-S1"])


def do_drop(number, course, term, confirmed=True, check_id=None):
    return drop_enrolment.fn(context=ctx(number), course_id=course, term=term, student_confirmed=confirmed,
                             check_id=check_id if check_id is not None else drop.check_id(number, course, term))


def test_dropping_after_a_check_returns_a_reference_and_the_notice(monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: date(2026, 9, 22))
    r = do_drop("S0000008", "COSC2148", "2027-S1")
    assert r["status"] == "dropped" and re.fullmatch(r"DROP-\d{6}", r["reference"]) and r["simulated"] is True
    assert "SIMULATION" in r["notice"] and r["dropped"]["course_id"] == "COSC2148"
    assert r["consequences"]["fee_outcome"] == "avoided"
    assert r == do_drop("S0000008", "COSC2148", "2027-S1")


def test_drop_needs_an_explicit_true_confirmation():
    for value in (False, None, "yes", 1, "true"):
        r = do_drop("S0000008", "COSC2148", "2027-S1", confirmed=value)
        assert r["status"] == "refused" and r["error"]["code"] == "NOT_CONFIRMED" and "SIMULATION" in r["notice"]
        assert "reference" not in r


def test_drop_needs_the_check_id_for_this_course_and_term():
    for wrong in ("", "abc", drop.check_id("S0000008", "COSC2462", "2027-S1"), drop.check_id("S0000001", "COSC2148", "2027-S1")):
        r = do_drop("S0000008", "COSC2148", "2027-S1", check_id=wrong)
        assert r["status"] == "refused" and r["error"]["code"] == "INVALID_CHECK" and "reference" not in r


def test_drop_is_refused_when_not_enrolled_or_after_the_deadline(monkeypatch):
    monkeypatch.setattr(drop, "melbourne_today", lambda: date(2026, 9, 22))
    r = do_drop("S0000001", "COSC2148", "2027-S1")
    assert r["status"] == "refused" and r["error"]["code"] == "NOT_ENROLLED"
    r = do_drop("S0000004", "COSC2110", "2026-S2")
    assert r["status"] == "refused" and r["error"]["code"] == "DROP_DEADLINE_PASSED" and "reference" not in r
    assert r["all_reasons"][0]["code"] == "DROP_DEADLINE_PASSED"


def test_checks_refuse_a_missing_login():
    r = check_drop.fn(context=AgentRun(request_context={}), course_id="COSC2148", term="2027-S1")
    assert r["found"] is False
    r = drop_enrolment.fn(context=None, course_id="COSC2148", term="2027-S1", check_id="x", student_confirmed=True)
    assert r["found"] is False


def test_a_student_can_only_drop_their_own_enrolment():
    r = call_check("S0000001", "COSC2148", "2027-S1")
    assert r["can_drop"] is False and r["summary"] is None


# State passed to the enrolment logic

def classes(course, term):
    parts = sch.components(sch.get_offering(course, term))
    return [next(o for o in parts["lecture"])["class_id"], next(o for o in parts["workshop"] if o["day"] == "Mon" and o["start"] == "18:00")["class_id"]]


def test_evaluate_with_no_state_is_the_record_alone():
    ids = classes("COSC2148", "2027-S1")
    student = STUDENTS["S0000001"]
    assert enr.evaluate(student, ids, []) == enr.evaluate(student, ids, [], extra_enrolments=[], dropped=[], taken={})


def test_an_enrolment_made_through_the_service_makes_a_second_one_already_enrolled():
    ids = classes("COSC2148", "2027-S1")
    made = [{"course_id": "COSC2148", "term": "2027-S1", "class_ids": ids}]
    r = enr.evaluate(STUDENTS["S0000001"], ids, [], extra_enrolments=made)
    assert r["eligible"] is False and [x["code"] for x in r["reasons"]] == ["ALREADY_ENROLLED"]


def test_a_dropped_record_enrolment_can_be_enrolled_again():
    ids = ["1015", "1102"]
    student = STUDENTS["S0000008"]
    assert "ALREADY_ENROLLED" in [x["code"] for x in enr.evaluate(student, ids, [])["reasons"]]
    again = enr.evaluate(student, ids, [], dropped=[("COSC2148", "2027-S1")])
    assert "ALREADY_ENROLLED" not in [x["code"] for x in again["reasons"]]


def reason_codes(student, ids, **state):
    return [x["code"] for x in enr.evaluate(student, ids, [], **state)["reasons"]]


def test_seats_taken_by_the_service_fill_a_class():
    student, workshop = STUDENTS["S0000001"], enr.find_class("1102")[2]
    assert "CLASS_FULL" not in reason_codes(student, ["1015", "1102"])
    assert "CLASS_FULL" in reason_codes(student, ["1015", "1102"], taken={"1102": workshop["seats_total"] - workshop["seats_taken"]})


def test_a_seat_freed_by_a_drop_reopens_a_full_class():
    student = STUDENTS["S0000001"]  # 1193 is the full COSC2148 lecture in 2027-S2
    assert "CLASS_FULL" in reason_codes(student, ["1193", "1194"])
    assert "CLASS_FULL" not in reason_codes(student, ["1193", "1194"], taken={"1193": -1})
