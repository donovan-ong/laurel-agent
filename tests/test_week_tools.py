from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.week_tools import get_my_week

# On 3 October 2026 (week 10 of Semester 2): S0000004 (Casey Delacroix) has Assignment 2 overdue in both
# current courses, Assignment 3 due 9 November, and an overdue library book that can be renewed. S0000007
# has an enrolment hold. S0000001 is admitted but not enrolled, so has no coursework or loans.
CASEY, HOLD, NOT_ENROLLED = "S0000004", "S0000007", "S0000001"
ON = "2026-10-03"


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def week(number, on=ON):
    return get_my_week.fn(context=ctx(number), on_date=on)


def test_nobody_logged_in_is_reported_plainly():
    r = get_my_week.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_a_bad_date_is_reported_plainly():
    assert week(CASEY, on="3 October")["found"] is False


def test_the_week_is_labelled_with_the_teaching_week():
    assert week(CASEY)["week_label"] == "Week 10, Semester 2 2026"


def test_overdue_work_comes_first_then_upcoming_then_the_plan_suggestion():
    items = week(CASEY)["items"]
    urgencies = [i["urgency"] for i in items]
    assert urgencies == sorted(urgencies, key=["action", "overdue", "today", "soon", "upcoming", "suggestion"].index)
    overdue = [i["title"] for i in items if i["urgency"] == "overdue"]
    assert overdue[:2] == ["Assignment 2 for Data Mining", "Assignment 2 for Machine Learning"]
    assert any("Computer Networks" in t for t in overdue)
    assert items[-1]["kind"] == "plan" and items[-1]["prompt"] == "Plan my study week"


def test_only_the_next_upcoming_due_date_is_listed():
    upcoming = [i for i in week(CASEY)["items"] if i["kind"] == "assignment" and i["urgency"] == "upcoming"]
    assert {i["when"] for i in upcoming} == {"2026-11-09"} and len(upcoming) == 2


def test_key_dates_within_four_weeks_are_included_with_days_to_go():
    exams = next(i for i in week(CASEY)["items"] if i["kind"] == "key_date")
    assert exams["title"] == "Semester 2 assessment period" and "in 23 days" in exams["detail"]


def test_a_hold_is_the_first_thing_shown():
    first = week(HOLD)["items"][0]
    assert first["kind"] == "hold" and first["urgency"] == "action" and "3600" in first["detail"]


def test_a_student_with_no_coursework_gets_no_assignments_and_no_plan_suggestion():
    kinds = {i["kind"] for i in week(NOT_ENROLLED)["items"]}
    assert "assignment" not in kinds and "plan" not in kinds and "loan" not in kinds


def test_every_item_has_a_prompt_to_ask_about_it():
    assert all(i["prompt"] and i["title"] for i in week(CASEY)["items"])


def test_another_students_work_never_appears():
    titles = " ".join(i["title"] for i in week(CASEY)["items"])
    assert "Cloud Security" not in titles  # S0000007's course

