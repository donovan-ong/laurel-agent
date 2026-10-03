import copy

import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import scheduling as sch
from tools.common import load
from tools.timetable_tools import check_availability_fit, find_courses_that_fit, get_timetable

CTX = AgentRun(request_context={"student_number": "S0000001"})
WORK = {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}
EVENING_OPTIONS_S2 = {"COSC2110", "INTE2402", "COSC2673"}


def option(day, start, end, mode="on_campus", **extra):
    return {"class_id": "1", "day": day, "start": start, "end": end, "mode": mode, "campus": "City",
            "seats_total": 30, "seats_taken": 10, "enrolment_open": True, **extra}


def workshops(course_id, term):
    return {w["class_id"]: w for w in sch.offering_fit(sch.get_offering(course_id, term), sch.parse_availability(WORK))["workshops"]}


# Availability

def test_availability_is_parsed_into_day_and_time_blocks():
    assert sch.parse_availability(WORK) == [(d, "09:00", "17:00") for d in ("Mon", "Tue", "Wed", "Thu", "Fri")]
    assert sch.parse_availability({"busy": [{"days": ["monday", "Sunday"], "start": "9:30", "end": "12:00"}]}) == [
        ("Mon", "09:30", "12:00"), ("Sun", "09:30", "12:00")]
    assert sch.parse_availability(None) == sch.parse_availability({}) == sch.parse_availability("") == []
    assert sch.parse_availability({"busy": []}) == []


@pytest.mark.parametrize("bad,message", [
    ("Mon 9 to 5", "availability must look like"),
    ({"busy": "Mon"}, "availability must look like"),
    ({"busy": [{"days": ["Funday"], "start": "09:00", "end": "17:00"}]}, "not a day"),
    ({"busy": [{"days": ["Mon"], "start": "nine", "end": "17:00"}]}, "not a time"),
    ({"busy": [{"days": ["Mon"], "start": "25:00", "end": "26:00"}]}, "not a time"),
    ({"busy": [{"days": ["Mon"], "start": "17:00", "end": "09:00"}]}, "start before it ends"),
    ({"busy": [{"days": [], "start": "09:00", "end": "17:00"}]}, "needs days"),
    ({"busy": [{"start": "09:00", "end": "17:00"}]}, "needs days"),
])
def test_bad_availability_is_explained(bad, message):
    with pytest.raises(sch.AvailabilityError, match=message):
        sch.parse_availability(bad)


def test_fit_labels_and_the_boundaries():
    blocks = sch.parse_availability(WORK)
    assert sch.fit(option("Mon", "17:00", "19:00"), blocks) == "fits"      # starts as work ends
    assert sch.fit(option("Mon", "07:00", "09:00"), blocks) == "fits"      # ends as work starts
    assert sch.fit(option("Mon", "16:59", "18:00"), blocks) == "clashes"
    assert sch.fit(option("Mon", "08:00", "09:01"), blocks) == "clashes"
    assert sch.fit(option("Sat", "10:00", "12:00"), blocks) == "fits"
    assert sch.fit(option(None, None, None), blocks) == "unknown"
    assert sch.fit(option("Mon", "10:00", "12:00", mode=None), blocks) == "unknown"
    assert sch.fit(option("Mon", "10:00", "12:00"), []) == "fits"


def test_available_needs_an_open_class_with_seats():
    assert sch.is_available(option("Mon", "10:00", "12:00"))
    assert not sch.is_available(option("Mon", "10:00", "12:00", enrolment_open=False))
    assert not sch.is_available(option("Mon", "10:00", "12:00", seats_taken=30))


def test_times_read_as_text():
    assert sch.when_text(option("Wed", "17:30", "19:30")) == "Wednesday 17:30 to 19:30"
    assert "to be confirmed" in sch.when_text(option(None, None, None))


# Course in a term

def test_a_course_with_an_evening_workshop_can_be_attended_by_a_nine_to_five_worker():
    r = sch.offering_fit(sch.get_offering("COSC2148", "2027-S1"), sch.parse_availability(WORK))
    fits = [w["when"] for w in r["workshops"] if w["fit"] == "fits"]
    assert r["can_attend"] == "yes" and fits and all("18:00" in w or "18:30" in w or "17" in w for w in fits)
    assert all(w["fit"] == "clashes" for w in r["workshops"] if w["start"] < "17:00")
    assert r["fitting_workshops"] == len(fits)


def test_a_daytime_only_course_cannot_be_attended_and_says_why():
    r = sch.offering_fit(sch.get_offering("COSC2814", "2027-S2"), sch.parse_availability(WORK))
    assert (r["can_attend"], r["reason"]) == ("no", "every workshop clashes") and r["fitting_workshops"] == 0
    assert sch.offering_fit(sch.get_offering("COSC2814", "2027-S2"), [])["can_attend"] == "yes"


def test_a_thesis_workshop_with_no_time_is_unknown_not_a_clash():
    r = sch.offering_fit(sch.get_offering("COSC3154", "2027-S1"), sch.parse_availability(WORK))
    assert r["can_attend"] == "unknown" and [w["fit"] for w in r["workshops"]] == ["unknown"]


def test_a_full_lecture_or_closed_term_means_no():
    full = sch.offering_fit(sch.get_offering("COSC2148", "2027-S2"), [])
    assert full["can_attend"] == "no" and "lecture" in full["reason"]
    closed = sch.offering_fit(sch.get_offering("COSC2110", "2026-S2"), [])
    assert closed["can_attend"] == "no"


def test_workshops_that_fit_but_are_full_do_not_count():
    offering = copy.deepcopy(sch.get_offering("COSC2148", "2027-S1"))  # loaded data is shared, so edit a copy
    for w in offering["components"][1]["options"]:
        w["seats_taken"] = w["seats_total"]
    assert sch.offering_fit(offering, sch.parse_availability(WORK))["reason"] == "the workshops that fit are full or closed"
    offering["components"][1]["options"][0]["seats_taken"] = 0  # a daytime one, still a clash
    assert sch.offering_fit(offering, [])["can_attend"] == "yes"


def test_the_suggested_lecture_is_the_open_one_with_most_free_seats():
    offering = copy.deepcopy(sch.get_offering("COSC2148", "2027-S1"))  # loaded data is shared, so edit a copy
    lectures = offering["components"][0]["options"]
    best = max(lectures, key=lambda o: o["seats_total"] - o["seats_taken"])
    assert sch.suggest_lecture(offering)["class_id"] == best["class_id"]
    for o in lectures:
        o["enrolment_open"] = False
    assert sch.suggest_lecture(offering) is None


def overlap(a, b):
    return a["day"] == b["day"] and a["start"] < b["end"] and b["start"] < a["end"]


def test_workshops_for_several_courses_are_chosen_without_overlaps():
    blocks = sch.parse_availability(WORK)
    chosen = sch.choose_workshops("2027-S1", ["COSC2148", "COSC2462"], blocks)
    a, b = chosen["COSC2148"], chosen["COSC2462"]
    assert sch.fit(a, blocks) == sch.fit(b, blocks) == "fits" and not overlap(a, b)


def test_times_already_taken_are_avoided_and_none_is_returned_when_nothing_fits():
    blocks = sch.parse_availability(WORK)
    free = sch.choose_workshops("2027-S1", ["COSC2148"], blocks)["COSC2148"]
    other = sch.choose_workshops("2027-S1", ["COSC2148"], blocks, taken=[(free["day"], free["start"], free["end"])])["COSC2148"]
    assert not overlap(free, other)
    everything = sch.parse_availability({"busy": [{"days": sch.DAY_ABBREVIATIONS, "start": "00:00", "end": "23:59"}]})
    assert sch.choose_workshops("2027-S1", ["COSC2148"], everything) is None
    assert sch.choose_workshops("2027-S1", ["NOPE"], []) is None


def test_workshops_that_fit_are_preferred_to_ones_with_no_time():
    chosen = sch.choose_workshops("2027-S1", ["COSC3154"], sch.parse_availability(WORK))
    assert chosen["COSC3154"]["day"] is None  # the only workshop has no time, so it is still usable


# The tools

def test_get_timetable_lists_lectures_workshops_and_seats():
    r = get_timetable.fn(course_id="COSC2148", term="2027-S1")
    assert r["found"] and r["course"]["title"] == "Computing Research and Project Preparation"
    offering = r["offerings"][0]
    hero = next(l for l in offering["lectures"] if l["class_id"] == "1015")
    assert (hero["when"], hero["mode"], hero["seats_left"], hero["full"]) == ("Wednesday 17:30 to 19:30", "online", 19, False)
    assert len(offering["workshops"]) == 5 and "recordings" in r["lecture_note"]
    assert offering["suggested_lecture"]["class_id"] in {l["class_id"] for l in offering["lectures"]}
    assert r["source"]["file"] == "timetable.json"


def test_get_timetable_takes_a_title_and_lists_every_term_without_a_term():
    r = get_timetable.fn(course_id="Data Mining")
    assert [o["term"] for o in r["offerings"]] == sch.offered_terms("COSC2110")
    assert get_timetable.fn(course_id="031749", term="2027-S1")["course"]["course_id"] == "COSC2148"


def test_get_timetable_explains_when_it_cannot_answer():
    not_offered = get_timetable.fn(course_id="Data Mining", term="2027-S1")
    assert not_offered["found"] is False and "It runs in: 2026-S2, 2027-S2, 2028-S2" in not_offered["reason"]
    assert get_timetable.fn(course_id="thesis")["ambiguous"] is True
    assert get_timetable.fn(course_id="COSC9999")["found"] is False


def test_a_closed_term_says_enrolment_is_closed():
    closed = get_timetable.fn(course_id="COSC2110", term="2026-S2")["offerings"][0]
    assert closed["enrolment_open"] is False and "Enrolment is closed for 2026-S2" in closed["enrolment_note"]
    open_term = get_timetable.fn(course_id="COSC2148", term="2027-S1")["offerings"][0]
    assert open_term["enrolment_open"] is True and open_term["enrolment_note"] is None


def test_the_closed_and_full_demo_classes_show_up_in_the_timetable():
    o = get_timetable.fn(course_id="COSC2148", term="2027-S2")["offerings"][0]
    assert [l["full"] for l in o["lectures"]] == [True] and o["suggested_lecture"] is None
    assert any(not w["enrolment_open"] for w in o["workshops"])
    assert all(not w["enrolment_open"] for w in get_timetable.fn(course_id="COSC2110", term="2026-S2")["offerings"][0]["workshops"])


def test_check_fit_labels_each_workshop_and_answers_yes_or_no():
    r = check_availability_fit.fn(course_id="COSC2148", availability=WORK, term="2027-S1")
    t = r["terms"][0]
    assert t["can_attend"] == "yes" and r["can_attend_in"] == ["2027-S1"] and r["unconfirmed_in"] == []
    assert {w["fit"] for w in t["workshops"]} == {"fits", "clashes"} and t["lectures"] and "lecture_note" in r
    robots = check_availability_fit.fn(course_id="Programming Autonomous Robots", availability=WORK, term="2027-S2")
    assert robots["terms"][0]["can_attend"] == "no" and robots["can_attend_in"] == []


def test_check_fit_over_every_term_and_with_no_limits():
    every = check_availability_fit.fn(course_id="COSC2148", availability=WORK)
    assert [t["term"] for t in every["terms"]] == sch.offered_terms("COSC2148")
    assert "2027-S2" not in every["can_attend_in"]  # its only lecture is full that term
    free = check_availability_fit.fn(course_id="COSC2814")
    assert free["can_attend_in"] == sch.offered_terms("COSC2814")[1:]  # 2026-S2 is closed


def test_check_fit_flags_thesis_as_unconfirmed():
    r = check_availability_fit.fn(course_id="COSC3155", availability=WORK, term="2027-S1")
    assert r["can_attend_in"] == [] and r["unconfirmed_in"] == ["2027-S1"]


def test_check_fit_reports_bad_availability_and_courses():
    bad = check_availability_fit.fn(course_id="COSC2148", availability={"busy": [{"days": ["Mon"], "start": "9am", "end": "5pm"}]})
    assert bad["found"] is False and "not a time" in bad["reason"] and "availability must look like" in bad["reason"]
    assert check_availability_fit.fn(course_id="nope", availability=WORK)["found"] is False
    assert check_availability_fit.fn(course_id="COSC2110", availability=WORK, term="2027-S1")["found"] is False


def test_find_courses_that_fit_lists_the_evening_option_courses():
    r = find_courses_that_fit.fn(context=CTX, term="2027-S2", availability=WORK, kind="option")
    assert {c["course_id"] for c in r["can_attend"]} == EVENING_OPTIONS_S2
    assert r["unconfirmed"] == [] and all(c["fitting_workshops"] for c in r["can_attend"])
    assert "cannot_attend" not in r and r["counts"]["can_attend"] == 3
    assert r["counts"]["offered"] == 10 == r["counts"]["can_attend"] + r["counts"]["cannot_attend"]


def test_the_daytime_only_course_is_listed_as_not_fitting_when_asked():
    r = find_courses_that_fit.fn(context=CTX, term="2027-S2", availability=WORK, kind="option", include_not_fitting=True)
    robots = next(c for c in r["cannot_attend"] if c["course_id"] == "COSC2814")
    assert robots["can_attend"] == "no" and robots["reason"] == "every workshop clashes"
    assert len(r["cannot_attend"]) == 7


def test_find_courses_by_kind_and_unconfirmed_thesis():
    compulsory = find_courses_that_fit.fn(context=CTX, term="2027-S1", availability=WORK, kind="compulsory")
    assert {c["course_id"] for c in compulsory["can_attend"]} == {"COSC2148", "COSC2462"}
    assert {c["course_id"] for c in compulsory["unconfirmed"]} == {"COSC3154", "COSC3155"}
    assert find_courses_that_fit.fn(context=CTX, term="2027-S1")["counts"]["offered"] == 4 + 11


def test_find_courses_rejects_bad_input():
    assert find_courses_that_fit.fn(context=CTX, term="2099-S1")["found"] is False
    assert find_courses_that_fit.fn(context=CTX, term="2027-S1", kind="fun")["found"] is False
    assert find_courses_that_fit.fn(context=CTX, term="2027-S1", availability="always")["found"] is False


def test_the_timetable_tools_are_read_only_and_take_no_student():
    for t in (get_timetable, check_availability_fit, find_courses_that_fit):
        props = set(t.__tool_spec__.input_schema.properties or {})
        assert not props & {"student_number", "student_id"} and t.__tool_spec__.permission.value == "read_only"
    assert "availability" in check_availability_fit.__tool_spec__.input_schema.properties


def test_option_courses_in_the_timetable_match_the_program():
    options = set(load("programs.json")[0]["option_list"]["course_ids"])
    r = find_courses_that_fit.fn(context=CTX, term="2027-S1", kind="option")
    assert {c["course_id"] for c in r["can_attend"]} <= options


# A result must say when no availability was applied

def test_fit_results_say_which_availability_was_used_and_warn_when_there_was_none():
    from tools.timetable_tools import check_availability_fit, find_courses_that_fit
    work = {"busy": [{"days": ["Mon", "Tue"], "start": "09:00", "end": "17:00"}]}
    none = check_availability_fit.fn(course_id="COSC2814", term="2027-S2")
    assert none["availability_used"].startswith("none given") and "call this tool again" in none["warning"]
    used = check_availability_fit.fn(course_id="COSC2814", term="2027-S2", availability=work)
    assert used["availability_used"] == ["Mon 09:00 to 17:00", "Tue 09:00 to 17:00"] and "warning" not in used
    assert "warning" in find_courses_that_fit.fn(context=CTX, term="2027-S2")
    assert "warning" not in find_courses_that_fit.fn(context=CTX, term="2027-S2", availability=work)
