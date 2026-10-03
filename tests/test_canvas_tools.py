import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.canvas_tools import list_assignments

# S0000004 (Casey Delacroix): a completed course (COSC2148/COSC2462, 2026-S1, both graded) and two current
# ones (COSC2110/COSC2673, 2026-S2). S0000001 (Donovan Ong): admitted but not enrolled in anything.
CASEY = "S0000004"
NOT_ENROLLED = "S0000001"
DEMO_DAY = "2026-10-03"  # the demo date: Assignment 2 is due the Sunday after next, 11 October, 11:59 pm
NEXT_WEEK = "2026-10-07"  # in the week (Mon 5 to Sun 11 October 2026) Assignment 2 is due in


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
    assert r["found"] is True and r["assignments"] == [] and r["date_used"]
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


def test_a_current_courses_second_assignment_is_not_yet_submitted():
    r = assignments(CASEY, course_id="COSC2110")
    second = next(a for a in r["assignments"] if a["title"] == "Assignment 2")
    assert (second["submitted"], second["submitted_at"], second["mark"]) == (False, None, None)
    first = next(a for a in r["assignments"] if a["title"] == "Assignment 1")
    assert first["submitted"] is True and isinstance(first["mark"], int)


def test_due_this_week_only_finds_assignment_2_in_its_week():
    r = assignments(CASEY, due_this_week_only=True, on_date=NEXT_WEEK)
    assert r["week"] == {"start": "2026-10-05", "end": "2026-10-11"}
    titles = {(a["course_id"], a["title"]) for a in r["assignments"]}
    assert ("COSC2110", "Assignment 2") in titles and ("COSC2673", "Assignment 2") in titles
    assert all(a["due_date"] == "2026-10-11" for a in r["assignments"])


def test_nothing_unsubmitted_is_overdue_on_the_demo_date():
    r = assignments(CASEY, on_date=DEMO_DAY)
    assert r["assignments"] and not any(a["due_status"].startswith("overdue") for a in r["assignments"])


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


def test_every_assignment_has_a_descriptive_title_and_a_one_sentence_summary():
    r = assignments(CASEY)
    assert all(a["name"] and a["full_title"] == f"{a['title']}: {a['name']}" for a in r["assignments"])
    assert all(a["summary"].endswith(".") and ". " not in a["summary"] for a in r["assignments"])


def test_the_first_data_mining_assignment_is_data_pre_processing():
    first = next(a for a in assignments(CASEY, course_id="COSC2110")["assignments"] if a["sequence"] == 1)
    assert first["full_title"] == "Assignment 1: Data Pre-processing"
    assert "missing values" in first["summary"]


def test_due_status_is_worked_out_from_today_not_the_snapshot_date():
    r = assignments(CASEY, course_id="COSC2110", on_date="2026-10-03")
    assert r["date_used"] == "2026-10-03"
    by_title = {a["title"]: a for a in r["assignments"]}
    second, third = by_title["Assignment 2"], by_title["Assignment 3"]
    assert (second["due_status"], second["days_until_due"]) == ("due in 8 days", 8)
    assert second["due_text"] == "Sunday 11 October 2026, 11:59 pm"
    assert third["due_status"] == "due in 37 days"
    assert by_title["Assignment 1"]["due_status"] == "submitted"


@pytest.mark.parametrize("on, expected", [("2026-10-11", "due today"), ("2026-10-10", "due tomorrow"),
                                          ("2026-10-12", "overdue by 1 day")])
def test_due_status_wording_near_the_due_date(on, expected):
    second = next(a for a in assignments(CASEY, course_id="COSC2110", on_date=on)["assignments"] if a["sequence"] == 2)
    assert second["due_status"] == expected


def test_a_bad_date_is_reported_plainly():
    r = assignments(CASEY, on_date="3 October")
    assert r["found"] is False and "on_date" in r["reason"]
