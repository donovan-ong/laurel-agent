import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.canvas_tools import list_assignments

# S0000004 (Casey Delacroix): a completed course (COSC2148/COSC2462, 2026-S1, both graded) and two current
# ones (COSC2110/COSC2673, 2026-S2). S0000001 (Donovan Ong): admitted but not enrolled in anything.
CASEY = "S0000004"
NOT_ENROLLED = "S0000001"
THIS_WEEK = "2026-10-01"  # lands in the week (Mon 28 Sep to Sun 4 Oct 2026) Assignment 2 is due in


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def assignments(number, **kwargs):
    return list_assignments.fn(context=ctx(number), **kwargs)


def test_nobody_logged_in_is_reported_plainly():
    r = list_assignments.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_an_unknown_course_is_reported_plainly():
    r = assignments(CASEY, course_id="NOPE1234")
    assert r["found"] is False and "NOPE1234" in r["reason"]


def test_a_student_not_enrolled_in_anything_has_no_assignments():
    r = assignments(NOT_ENROLLED)
    assert r == {"found": True, "assignments": [], "source": r["source"]}
    assert r["source"]["file"] == "canvas.json"


def test_assignments_are_listed_in_due_date_order_across_every_course():
    r = assignments(CASEY)
    dates = [a["due_date"] for a in r["assignments"]]
    assert dates == sorted(dates)
    assert {a["course_id"] for a in r["assignments"]} == {"COSC2148", "COSC2462", "COSC2110", "COSC2673"}


def test_course_id_filters_to_just_that_course():
    r = assignments(CASEY, course_id="COSC2148")
    assert [a["course_id"] for a in r["assignments"]] == ["COSC2148"] * 3
    assert r["assignments"][0]["course_title"]


def test_a_completed_courses_assignments_are_all_submitted_and_graded():
    r = assignments(CASEY, course_id="COSC2148")
    for a in r["assignments"]:
        assert a["submitted"] is True
        assert a["submitted_at"] is not None
        assert isinstance(a["mark"], int) and 0 <= a["mark"] <= a["max_mark"]


def test_a_current_courses_second_assignment_is_overdue_and_not_yet_submitted():
    r = assignments(CASEY, course_id="COSC2110")
    second = next(a for a in r["assignments"] if a["title"] == "Assignment 2")
    assert (second["submitted"], second["submitted_at"], second["mark"]) == (False, None, None)
    first = next(a for a in r["assignments"] if a["title"] == "Assignment 1")
    assert first["submitted"] is True and isinstance(first["mark"], int)


def test_due_this_week_only_finds_the_overdue_assignment_around_the_demo_date():
    r = assignments(CASEY, due_this_week_only=True, on_date=THIS_WEEK)
    assert r["week"] == {"start": "2026-09-28", "end": "2026-10-04"}
    titles = {(a["course_id"], a["title"]) for a in r["assignments"]}
    assert ("COSC2110", "Assignment 2") in titles and ("COSC2673", "Assignment 2") in titles
    assert all(a["due_date"] == "2026-09-28" for a in r["assignments"])


def test_due_this_week_only_is_empty_for_a_quiet_week():
    r = assignments(CASEY, due_this_week_only=True, on_date="2026-12-25")
    assert r["assignments"] == []


def test_an_invalid_on_date_is_reported_plainly():
    r = assignments(CASEY, due_this_week_only=True, on_date="not-a-date")
    assert r["found"] is False


def test_a_students_assignments_never_include_another_students():
    from tools.common import load
    raw = load("canvas.json")
    r = assignments(CASEY)
    expected = {a["assignment_id"] for a in raw if a["student_number"] == CASEY}
    assert {a["assignment_id"] for a in r["assignments"]} == expected
    assert expected  # the fixture actually has some, or this test proves nothing
