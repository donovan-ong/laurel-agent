from datetime import date

import pytest

from tools import calendar_tools, common
from tools.calendar_tools import get_current_week, get_key_dates

TODAY = "2026-09-21"


def week(on_date):
    return get_current_week.fn(on_date=on_date)


def events(**kwargs):
    kwargs.setdefault("on_date", TODAY)
    return get_key_dates.fn(**kwargs)


# What week is it

def test_a_teaching_week_is_named_with_its_dates():
    r = week(TODAY)
    assert (r["date"], r["weekday"], r["in_teaching_week"]) == (TODAY, "Monday", True)
    assert r["teaching_weeks"] == [{"period": "2026-S2", "name": "Semester 2 2026", "week": "Week 9",
                                    "week_start": "2026-09-21", "week_end": "2026-09-27",
                                    "when": "Monday 21 September 2026 to Sunday 27 September 2026"}]
    assert r["source"]["provenance"] == "mixed" and r["source"]["file"] == "key_dates.json"


@pytest.mark.parametrize("on_date,expected", [
    ("2026-03-02", "Week 1"), ("2026-03-08", "Week 1"), ("2026-03-09", "Week 2"), ("2026-06-28", "Week 16"),
    ("2026-07-20", "Week 1"), ("2026-08-30", "Week 6"), ("2026-11-15", "Week 16"),
])
def test_week_boundaries(on_date, expected):
    assert [w["week"] for w in week(on_date)["teaching_weeks"]] == [expected]


def test_the_mid_semester_break_wins_over_the_week_it_overlaps():
    # The Semester 1 week table lists Week 5 as 30 March to 5 April and the break as 3 to 12 April
    assert [w["week"] for w in week("2026-04-02")["teaching_weeks"]] == ["Week 5"]
    for day in ("2026-04-03", "2026-04-04", "2026-04-12"):
        r = week(day)
        assert [w["week"] for w in r["teaching_weeks"]] == ["Mid-semester break"] and r["in_teaching_week"] is False
    assert [w["week"] for w in week("2026-04-13")["teaching_weeks"]] == ["Week 6"]
    assert [w["week"] for w in week("2026-09-03")["teaching_weeks"]] == ["Mid-semester break"]


def test_semester_break_is_not_a_teaching_week_and_lists_what_is_happening():
    r = week("2026-07-15")
    assert r["teaching_weeks"] == [] and r["in_teaching_week"] is False
    happening = {e["event"] for e in r["happening_now"]}
    assert {"Semester break", "Mid-year orientation"} <= happening


def test_holiday_closure_events_are_listed_once_with_every_period_they_appear_under():
    r = week("2026-12-25")
    assert r["teaching_weeks"] == []
    closure = [e for e in r["happening_now"] if e["event"] == "RMIT University closed"]
    assert len(closure) == 1 and closure[0]["periods"] == ["2026-S2"]
    assert any("Christmas Day" in e["event"] for e in r["happening_now"])
    winter = week("2025-12-30")
    assert [e["periods"] for e in winter["happening_now"] if e["event"] == "RMIT University closed"] == [
        ["2026-S1", "2025-SPR", "2026-SUM"]]


def test_next_events_count_the_days_to_go():
    upcoming = week(TODAY)["next_events"]
    assert [(e["date"], e["days_until_start"]) for e in upcoming[:3]] == [
        ("2026-09-25", 4), ("2026-10-01", 10), ("2026-10-09", 18)]
    assert "AFL Grand Final" in upcoming[0]["event"] and all(e["status"] == "upcoming" for e in upcoming)


def test_next_event_of_each_main_kind():
    nxt = week(TODAY)["next_by_category"]
    assert set(nxt) == {"holiday", "census", "drop_deadline", "assessment_period", "results_release",
                        "classes_begin", "enrolment_opens"}
    assert "withdraw_deadline" not in nxt  # nothing of that kind is left after 21 September
    assert {k: (v["date"], v["days_until_start"]) for k, v in nxt.items()} == {
        "holiday": ("2026-09-25", 4), "enrolment_opens": ("2026-10-01", 10), "assessment_period": ("2026-10-26", 35),
        "results_release": ("2026-11-30", 70), "classes_begin": ("2026-11-16", 56), "census": ("2026-12-07", 77),
        "drop_deadline": ("2027-01-22", 123)}


def test_the_uni_break_is_never_a_public_holiday():
    r = week(TODAY)
    # The mid-semester break has just ended, so the next break is the closure over the holidays
    assert (r["previous_break"]["event"], r["previous_break"]["date"], r["previous_break"]["end_date"],
            r["previous_break"]["days_until_end"]) == ("Mid-semester break", "2026-08-31", "2026-09-06", -15)
    assert (r["next_break"]["category"], r["next_break"]["date"], r["next_break"]["end_date"],
            r["next_break"]["days_until_start"]) == ("university_closure", "2026-12-25", "2027-01-01", 95)
    assert "AFL" not in r["next_break"]["event"] and r["next_break"]["category"] in ("break", "university_closure")
    # Earlier in the semester the mid-semester break is still to come, and during it the break is happening now
    early = week("2026-08-20")
    assert (early["next_break"]["date"], early["next_break"]["status"]) == ("2026-08-31", "upcoming")
    assert early["previous_break"]["event"] == "Semester break"
    during = week("2026-09-03")
    assert (during["next_break"]["event"], during["next_break"]["status"]) == ("Mid-semester break", "happening_now")
    over_summer = week("2026-12-30")
    assert over_summer["next_break"]["status"] == "happening_now" and over_summer["next_break"]["category"] == "university_closure"
    assert week("2027-01-10")["next_break"] is None and week("2027-01-10")["previous_break"]["date"] == "2026-12-25"


def test_today_comes_from_the_melbourne_clock_when_no_date_is_given(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 10, 26))
    r = get_current_week.fn()
    assert r["date_from"] == "clock (Melbourne)" and r["date"] == "2026-10-26"
    assert [w["week"] for w in r["teaching_weeks"]] == ["Week 14"]
    assert "Semester 2 assessment period" in {e["event"] for e in r["happening_now"]}
    assert week("2026-10-26")["date_from"] == "provided"


def test_dates_outside_the_published_calendar_or_malformed_are_not_found():
    for outside in ("2025-08-31", "2027-02-27", "2030-01-01"):
        r = week(outside)
        assert r["found"] is False and "2025-09-01" in r["reason"] and "2027-02-26" in r["reason"]
    assert week("2026-09-21")["found"] is True and week("2025-09-01")["found"] is True and week("2027-02-26")["found"] is True
    for bad in ("tomorrow", "21/09/2026", "2026-13-01"):
        assert week(bad)["found"] is False and "on_date must look like" in week(bad)["reason"]


# Looking up dates

def test_exam_period_and_results_release_with_days_to_go():
    exams = events(category="assessment_period", upcoming_only=True)["events"]
    assert [(e["date"], e["end_date"], e["days_until_start"], e["days_until_end"], e["periods"]) for e in exams] == [
        ("2026-10-26", "2026-11-13", 35, 53, ["2026-S2"]), ("2027-02-15", "2027-02-19", 147, 151, ["2026-SPR"])]
    results = events(period="2026-S2", category="results_release")["events"]
    assert [(e["date"], e["days_until_start"], e["status"]) for e in results] == [("2026-11-30", 70, "upcoming")]


def test_the_break_that_has_passed_is_marked_past():
    r = events(period="2026-S2", category="break")["events"]
    assert [(e["date"], e["end_date"], e["status"], e["days_until_start"], e["days_until_end"]) for e in r] == [
        ("2026-08-31", "2026-09-06", "past", -21, -15)]
    assert events(period="2026-S2", category="break", upcoming_only=True)["found"] is False


def test_an_event_in_progress_is_happening_now():
    r = events(period="2026-S2", category="assessment_period", on_date="2026-11-02")["events"][0]
    assert (r["status"], r["days_until_start"], r["days_until_end"]) == ("happening_now", -7, 11)


def test_the_corrected_break_carries_its_note_and_other_events_have_none():
    brk = events(period="2026-S1", category="break", on_date="2026-04-05")["events"]
    mid = next(e for e in brk if "Mid-semester" in e["event"])
    assert (mid["date"], mid["end_date"], mid["status"]) == ("2026-04-03", "2026-04-12", "happening_now")
    assert "3 to 12 April" in mid["note"] and "Friday 3 to Friday 10 April" in mid["note"]
    assert next(e for e in brk if e["event"] == "Semester break")["note"] is None
    assert events(period="2026-S2", category="census")["events"][0]["note"] is None
    assert [e["note"] for e in week("2026-04-05")["happening_now"] if "Mid-semester" in e["event"]] == [mid["note"]]


def test_add_deadlines_say_which_schools_they_are_for():
    r = events(period="2026-S2", category="add_deadline")["events"]
    assert [(e["date"], e["applies_to"]) for e in r] == [
        ("2026-07-27", "art_architecture_fashion_only"), ("2026-08-02", "all_other_schools")]


def test_census_and_withdrawal_dates_for_semester_2():
    assert events(period="2026-S2", category="census")["events"][0]["date"] == "2026-08-31"
    withdraw = events(period="2026-S2", category="withdraw_deadline")["events"][0]
    assert (withdraw["date"], withdraw["status"]) == ("2026-09-18", "past")
    assert events(period="2026-S2", category="enrolment_opens")["events"][0]["date"] == "2026-10-01"


def test_results_for_semester_1_and_the_other_periods():
    assert events(period="2026-S1", category="results_release")["events"][0]["date"] == "2026-07-13"
    assert events(period="2025-SPR", category="results_release")["events"][0]["date"] == "2026-02-27"
    assert events(period="2026-SUM", category="census")["events"][0]["date"] == "2026-01-13"
    assert events(period="2026-SPR", category="classes_begin")["events"][0]["date"] == "2026-11-16"


def test_results_release_across_periods_is_in_date_order():
    dates = [e["date"] for e in events(category="results_release")["events"]]
    assert dates == sorted(dates) and len(dates) == 5


def test_limit_and_more_available():
    r = events(category="holiday", limit=3)
    assert len(r["events"]) == 3 and r["more_available"] is True
    assert events(category="holiday", limit=100)["more_available"] is False


def test_week_table_on_request():
    r = events(period="2026-S2", category="census", include_weeks=True)
    assert list(r["weeks"]) == ["2026-S2"] and len(r["weeks"]["2026-S2"]) == 17
    assert "weeks" not in events(period="2026-S2", category="census")
    assert set(events(category="census", include_weeks=True)["weeks"]) == {"2026-S1", "2026-S2"}
    assert events(period="2026-SPR", category="census", include_weeks=True)["weeks"] == {}


def test_unknown_filters_and_empty_results_are_not_found():
    bad_period = events(period="2027-S1")
    assert bad_period["found"] is False and "2026-S2" in bad_period["reason"]
    bad_category = events(category="parties")
    assert bad_category["found"] is False and "assessment_period" in bad_category["reason"]
    assert events(period="2026-S1", category="graduation") == {"found": False, "reason": "No key dates match those filters."}
    assert events(on_date="soon")["found"] is False


def test_key_date_tools_need_no_login_and_take_no_student():
    for t in (get_current_week, get_key_dates):
        properties = set((t.__tool_spec__.input_schema.properties or {}))
        assert "context" not in properties and not properties & {"student_number", "student_id"}
        assert t.__tool_spec__.permission.value == "read_only"


def test_tool_descriptions_list_every_period_and_category_in_the_data():
    doc = get_key_dates.__tool_spec__.description
    for period in {p["period"] for p in common.load("key_dates.json")}:
        assert period in doc
    for category in {e["category"] for p in common.load("key_dates.json") for e in p["events"]}:
        assert category in doc
    assert "exam" in doc and "results" in doc and "break" in doc


def test_merged_events_are_unique_and_sorted():
    merged = calendar_tools.merged_events()
    keys = [(e["date"], e["end_date"], e["event"]) for e in merged]
    assert len(keys) == len(set(keys)) and keys == sorted(keys, key=lambda k: (k[0], k[1] or k[0], k[2]))
    assert len(merged) < sum(len(p["events"]) for p in common.load("key_dates.json"))


def test_events_carry_the_dates_as_text_to_quote():
    exams = events(category="assessment_period", upcoming_only=True)["events"]
    assert exams[0]["when"] == "Monday 26 October 2026 to Friday 13 November 2026"
    holiday = events(period="2026-S2", category="holiday", upcoming_only=True)["events"][0]
    assert holiday["when"] == "Friday 25 September 2026"
    closure = week(TODAY)["next_break"]
    assert closure["when"] == "Friday 25 December 2026 to Friday 1 January 2027"
    assert week("2026-09-03")["happening_now"][0]["when"] == "Monday 31 August 2026 to Sunday 6 September 2026"


def test_the_current_week_and_the_date_have_text_too():
    r = week(TODAY)
    assert r["date_text"] == "Monday 21 September 2026"
    assert r["teaching_weeks"][0]["when"] == "Monday 21 September 2026 to Sunday 27 September 2026"


def test_every_when_text_agrees_with_its_iso_dates():
    from datetime import date as d
    for e in calendar_tools.merged_events():
        text = calendar_tools.annotate(e, d(2026, 9, 21))["when"]
        start = d.fromisoformat(e["date"])
        assert text.startswith(f"{calendar_tools.DAY_NAMES[start.weekday()]} {start.day} {start.strftime('%B %Y')}")
        assert (" to " in text) == (e["end_date"] not in (None, e["date"]))


def test_the_description_tells_the_model_to_quote_the_when_text():
    assert "quote it as it is" in get_key_dates.__tool_spec__.description
