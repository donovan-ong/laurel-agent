import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import study_week
from tools.common import load
from tools.studyspaces import is_free
from tools.week_tools import get_my_week, plan_study_week

# On 3 October 2026 (week 10 of Semester 2, the demo date): S0000004 (Casey Delacroix) has Assignment 2 due
# Sunday 11 October, 11:59 pm in both current courses (the priority, not yet overdue), Assignment 3 due
# 9 November, and an overdue library book that can be renewed. S0000007
# has an enrolment hold. S0000001 is admitted but not enrolled, so has no coursework or loans.
CASEY, HOLD, NOT_ENROLLED = "S0000004", "S0000007", "S0000001"
ON = "2026-10-03"
WORK_HOURS = {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def week(number, on=ON):
    return get_my_week.fn(context=ctx(number), on_date=on)


def plan(number, on=ON, **kwargs):
    return plan_study_week.fn(context=ctx(number), on_date=on, **kwargs)


@pytest.mark.parametrize("tool", [get_my_week, plan_study_week])
def test_nobody_logged_in_is_reported_plainly(tool):
    r = tool.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_a_bad_date_is_reported_plainly():
    assert week(CASEY, on="3 October")["found"] is False


def test_the_week_is_labelled_with_the_teaching_week():
    assert week(CASEY)["week_label"] == "Week 10, Semester 2 2026"


def test_the_most_urgent_items_come_first_then_upcoming_then_the_plan_suggestion():
    items = week(CASEY)["items"]
    urgencies = [i["urgency"] for i in items]
    assert urgencies == sorted(urgencies, key=["action", "overdue", "today", "soon", "upcoming", "suggestion"].index)
    soon = [i for i in items if i["urgency"] == "soon"]
    assert [i["title"] for i in soon] == ["Assignment 2: Classification Models (Data Mining)",
                                          "Assignment 2: Classification with Neural Networks (Machine Learning)"]
    assert "Sunday 11 October 2026, 11:59 pm (in 8 days)" in soon[0]["detail"]
    assert [i["kind"] for i in items if i["urgency"] == "overdue"] == ["loan"]  # no assignment is overdue
    assert items[-1]["kind"] == "plan" and items[-1]["prompt"] == "Plan my study week"


def test_upcoming_items_are_in_date_order():
    upcoming = [i["when"] for i in week(CASEY)["items"] if i["urgency"] == "upcoming"]
    assert upcoming == sorted(upcoming)


def test_work_left_past_its_due_date_is_still_flagged_overdue():
    items = week(CASEY, on="2026-10-13")["items"]
    assert [i["title"] for i in items if i["urgency"] == "overdue" and i["kind"] == "assignment"][:1] == [
        "Assignment 2: Classification Models (Data Mining)"]


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


def test_assignment_prompts_name_the_specific_assignment():
    prompts = [i["prompt"] for i in week(CASEY)["items"] if i["kind"] == "assignment"]
    assert "Did I submit Assignment 2: Classification Models for Data Mining?" in prompts
    assert "What is Assignment 3: Clustering and Association Rules for Data Mining about?" in prompts


def test_every_item_has_a_prompt_to_ask_about_it():
    assert all(i["prompt"] and i["title"] for i in week(CASEY)["items"])


def test_another_students_work_never_appears():
    titles = " ".join(i["title"] for i in week(CASEY)["items"])
    assert "Cloud Security" not in titles  # S0000007's course


def test_the_plan_puts_the_most_urgent_work_first():
    sessions = plan(CASEY)["sessions"]
    assert sessions and all(s["assignment"].startswith("Assignment 2") for s in sessions[:4])
    assert {s["course_id"] for s in sessions[:4]} == {"COSC2110", "COSC2673"}
    assert not any(s["overdue"] for s in sessions)


def test_the_plan_avoids_the_students_own_workshops():
    r = plan(CASEY)
    assert r["busy_used"] == ["COSC2110 workshop: Mon 18:00 to 20:00", "COSC2673 workshop: Wed 18:00 to 20:00"]
    assert not any(s["weekday"] in ("Mon", "Wed") and s["start"] == "19:00" for s in r["sessions"])


def test_the_plan_respects_stated_commitments():
    r = plan(CASEY, availability=WORK_HOURS)
    weekday_daytime = [s for s in r["sessions"] if s["weekday"] not in ("Sat", "Sun") and s["start"] < "17:00"]
    assert r["sessions"] and not weekday_daytime


def test_the_plan_keeps_to_two_sessions_a_day_and_the_session_limit():
    r = plan(CASEY, max_sessions=4)
    assert len(r["sessions"]) == 4
    days = [s["date"] for s in r["sessions"]]
    assert all(days.count(d) <= study_week.MAX_PER_DAY for d in days)


def test_work_due_today_can_still_be_planned_for_today():
    r = plan(CASEY, on="2026-10-11")
    assert any(s["date"] == "2026-10-11" and s["assignment"] == "Assignment 2: Classification Models" for s in r["sessions"])


def test_suggested_rooms_are_free_for_their_session():
    spaces = load("study_spaces.json")
    for on in ("2026-09-28", ON):
        for s in plan(CASEY, on=on)["sessions"]:
            assert s["room"] and is_free(s["room"]["room_id"], s["date"], s["start"], s["end"], spaces["bookings"])


def test_nothing_to_plan_is_an_empty_plan_not_an_error():
    r = plan(NOT_ENROLLED)
    assert r["found"] is True and r["sessions"] == [] and r["unscheduled"] == []


def test_the_plan_says_nothing_was_booked():
    assert "nothing has been booked" in plan(CASEY)["note"]


def test_malformed_availability_is_reported_with_the_format():
    r = plan(CASEY, availability={"busy": "weekdays"})
    assert r["found"] is False and "busy" in r["reason"]
