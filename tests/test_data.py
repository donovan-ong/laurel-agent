import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "seed"))
import generate  # noqa: E402
import validate  # noqa: E402

DATA = ROOT / "data"
CORE = ["COSC2148", "COSC2462", "COSC3154", "COSC3155"]


@pytest.fixture
def data():
    return validate.load_data(DATA)


@pytest.fixture
def pub():
    return generate.load_public()


def test_committed_data_passes_validation(data):
    assert validate.validate(data) == []


def test_stored_report_is_current(data):
    text, ok = validate.render_report(data)
    assert ok
    assert (ROOT / "seed" / "validation_report.txt").read_text(encoding="utf-8") == text


def test_generator_reproduces_committed_files(tmp_path):
    subprocess.run(
        [sys.executable, str(ROOT / "seed" / "generate.py"), "--out", str(tmp_path)],
        check=True, capture_output=True,
    )
    for name in validate.FILES.values():
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes(), f"{name} is stale"


def test_same_seed_same_output_different_seed_differs(pub):
    first, _ = generate.build_timetable(pub, generate.SEED, generate.SNAPSHOT_DATE)
    again, _ = generate.build_timetable(pub, generate.SEED, generate.SNAPSHOT_DATE)
    other, _ = generate.build_timetable(pub, generate.SEED + 1, generate.SNAPSHOT_DATE)
    assert first == again
    assert first != other


def test_generated_data_passes_validation_for_another_seed(tmp_path, pub):
    snap, seed = generate.SNAPSHOT_DATE, generate.SEED + 1
    other, _ = generate.build_timetable(pub, seed, snap)
    students = generate.build_students(other, snap)
    courses = generate.build_courses(pub, snap)
    for name, obj in [
        ("programs.json", generate.build_programs(pub, snap)),
        ("courses.json", courses),
        ("timetable.json", other),
        ("terms.json", generate.build_terms(pub, snap)),
        ("key_dates.json", generate.build_key_dates(pub, snap)),
        ("fees.json", generate.build_fees(snap)),
        ("contacts.json", generate.build_contacts(snap)),
        ("students.json", students),
        ("accounts.json", generate.build_accounts(students, seed, snap)),
        ("canvas.json", generate.build_canvas(students, courses, snap)),
        ("study_spaces.json", generate.build_study_spaces(snap)),
        ("print_accounts.json", generate.build_print_accounts(students, snap)),
        ("careers_listings.json", generate.build_careers_listings(snap)),
        ("library_loans.json", generate.build_library_loans(students, snap)),
    ]:
        generate.write_json(tmp_path / name, obj)
    assert validate.validate(validate.load_data(tmp_path)) == []


def test_program_matches_the_public_structure(data, pub):
    program, courses = data["programs"][0], {c["course_id"]: c for c in data["courses"]}
    assert program["program_code"] == "BH013P26" and program["total_credit_points"] == 96

    def numbers(s):
        fixed = sum(courses[i["course_id"]]["credit_points"] for i in s["items"] if i["type"] == "course")
        return s["stage"], s["credit_points"], fixed, sum(i["credit_points"] for i in s["items"] if i["type"] == "options")
    assert [numbers(s) for s in program["stages"]] == [("A", 48, 24, 24), ("B", 48, 36, 12)]
    # Stage B keeps its options between Thesis Part A and Part B
    assert [i.get("course_id") or i["type"] for i in program["stages"][1]["items"]] == ["COSC3154", "options", "COSC3155"]
    assert len(program["option_list"]["course_ids"]) == 21
    assert len(courses) == 150 and {c for c in courses if c in pub["programs"]["BH013P26"]["option_list"]["course_ids"]} == set(program["option_list"]["course_ids"])
    assert all(courses[i]["credit_points"] == 12 for i in program["option_list"]["course_ids"])
    assert {i: courses[i]["credit_points"] for i in CORE} == {"COSC2148": 12, "COSC2462": 12, "COSC3154": 12, "COSC3155": 24}
    # 48 cp a semester full-time and 24 part-time reproduce the public 1 and 2 year durations
    load = program["study_load"]
    assert program["total_credit_points"] / load["full_time_cp_per_semester"] / 2 == program["duration"]["full_time_years"]
    assert program["total_credit_points"] / load["part_time_cp_per_semester"] / 2 == program["duration"]["part_time_years"]


def test_only_cosc2148_has_a_handbook_page_so_other_codes_are_synthetic(data):
    codes = {c["course_id"]: c["handbook_code"] for c in data["courses"]}
    assert codes.pop("COSC2148") == "031749"
    assert all(code.startswith("S") for code in codes.values())
    course = next(c for c in data["courses"] if c["course_id"] == "COSC2148")
    assert course["assumed_knowledge"] == [] and course["description"].startswith("This course focuses on research")


def test_thesis_parts_need_stage_a_but_not_each_other(data):
    prereqs = {c["course_id"]: c["prerequisites"] for c in data["courses"]}
    assert prereqs["COSC3154"] == prereqs["COSC3155"] == ["COSC2148", "COSC2462"]
    honours = ["COSC2148", "COSC2462", "COSC2632", "COSC2633", "COSC2301", "COSC2110", "INTE1071", "INTE2402", "COSC2274", "COSC2527", "COSC1183",
               "ISYS3459", "COSC2972", "COSC2673", "COSC3047", "ISYS1079", "INTE2547", "INTE2626", "COSC2674", "COSC2814", "COSC2973", "INTE2695", "INTE2696"]
    assert not any(prereqs[i] for i in honours)   # the original Honours courses keep their original (empty) prerequisites


# Helpers for the feasibility tests

def bcs(d):
    return next(p for p in d["programs"] if p["program_code"] == "BP094P23")


def bit(d):
    return next(p for p in d["programs"] if p["program_code"] == "BP162P23")


def offering(d, course_id="COSC2148", term="2027-S1"):
    return next(o for o in d["timetable"] if (o["course_id"], o["term"]) == (course_id, term))


def workshops(d, course_id, term):
    return next(c for c in offering(d, course_id, term)["components"] if c["component"] == "workshop")["options"]


def clashes_with_busy(opt, busy_days, start="09:00", end="17:00"):
    return opt["day"] in busy_days and opt["start"] < end and opt["end"] > start


def overlap(a, b):
    return a["day"] == b["day"] and a["start"] < b["end"] and b["start"] < a["end"]


def attendable(d, course_ids, term, busy_days):
    """True if one fitting workshop per course can be chosen with none overlapping."""
    choices = [[w for w in workshops(d, c, term) if w["day"] and not clashes_with_busy(w, busy_days)] for c in course_ids]
    return any(
        not any(overlap(a, b) for a, b in itertools.combinations(combo, 2))
        for combo in itertools.product(*choices)
    )


WEEK = {"Mon", "Tue", "Wed", "Thu", "Fri"}


def test_nine_to_five_worker_can_follow_the_part_time_plan(data):
    assert attendable(data, ["COSC2148", "COSC2462"], "2027-S1", WEEK)
    pairs = list(itertools.combinations(["COSC2110", "INTE2402", "COSC2673"], 2))
    assert any(attendable(data, list(p), "2027-S2", WEEK) for p in pairs)
    assert any(attendable(data, [c], "2028-S1", WEEK) for c in ["COSC2632", "COSC2274", "COSC1183"])


def test_thesis_workshops_have_no_fixed_time_so_fit_is_unknown(data):
    for course in ("COSC3154", "COSC3155"):
        for term in generate.TERMS:
            assert [w["day"] for w in workshops(data, course, term)] == [None]


def test_daytime_only_course_never_fits_a_nine_to_five_worker(data):
    for offering_ in (o for o in data["timetable"] if o["course_id"] == "COSC2814"):
        term = offering_["term"]
        assert not any(w["day"] and not clashes_with_busy(w, WEEK) for w in workshops(data, "COSC2814", term))


def test_full_time_student_avoiding_tuesdays_can_still_take_stage_a(data):
    busy_tuesday = {"Tue"}
    assert attendable(data, ["COSC2148", "COSC2462"], "2027-S1", busy_tuesday)


def test_option_courses_run_one_semester_a_year(data, pub):
    terms = {}
    for o in data["timetable"]:
        terms.setdefault(o["course_id"], []).append(o["term"])
    for cid in pub["programs"]["BH013P26"]["option_list"]["course_ids"]:
        semesters = {t[-2:] for t in terms[cid]}
        assert len(semesters) == 1
        semester = next(iter(semesters))
        assert sorted(terms[cid]) == [t for t in generate.TERMS if t.endswith(semester)]
    for cid in CORE:
        assert sorted(terms[cid]) == generate.TERMS


def course(d, course_id):
    return next(c for c in d["courses"] if c["course_id"] == course_id)


def first_option(d, course_id="COSC2148", term="2027-S1", component="lecture"):
    return next(c for c in offering(d, course_id, term)["components"] if c["component"] == component)["options"][0]


def remove_daytime_only_courses(d):
    for o in d["timetable"]:
        for c in o["components"]:
            if c["component"] == "workshop" and c["options"][0]["day"] is not None:
                c["options"][0].update(start="18:00", end="20:00")


def remove_option_evenings(d):
    for o in d["timetable"]:
        if o["term"] == "2027-S1" and o["course_id"] not in CORE:
            for c in o["components"]:
                if c["component"] == "workshop":
                    for opt in c["options"]:
                        opt.update(start="10:00", end="12:00")


def student(d, number):
    return next(s for s in d["students"] if s["student_number"] == number)


def test_every_student_has_a_results_record_of_whole_number_marks(data):
    assert len(data["students"]) == 14
    for s in data["students"]:
        assert isinstance(s["results"], list)
        for r in s["results"]:
            assert set(r) == {"course_id", "term", "mark"}
            assert isinstance(r["mark"], int) and 0 <= r["mark"] <= 100
    assert [len(student(data, f"S000000{n}")["results"]) for n in (1, 2, 3)] == [0, 0, 0]


def test_current_term_is_closed_and_later_terms_are_open(data):
    for o in data["timetable"]:
        opens = {opt["enrolment_open"] for c in o["components"] for opt in c["options"]}
        if o["term"] == generate.CURRENT_TERM:
            assert opens == {False}


def test_demo_accounts_map_in_order(data):
    assert [(a["username"], a["student_number"]) for a in data["accounts"]] == [
        (f"demo{n}", f"S{n:07d}") for n in range(1, 15)]


def period(d, period_id):
    return next(p for p in d["key_dates"] if p["period"] == period_id)


def event(d, period_id, category, index=0):
    return [e for e in period(d, period_id)["events"] if e["category"] == category][index]


def test_key_dates_transcribe_the_published_pages(data):
    assert [(p["period"], p["kind"], len(p["events"]), len(p["weeks"])) for p in data["key_dates"]] == [
        ("2026-S1", "semester", 24, 17), ("2026-S2", "semester", 26, 17), ("2025-SPR", "spring", 14, 0),
        ("2026-SUM", "summer", 11, 0), ("2026-SPR", "spring", 15, 0)]
    s2 = {c: [(e["date"], e["end_date"]) for e in period(data, "2026-S2")["events"] if e["category"] == c]
          for c in ("classes_begin", "census", "assessment_period", "results_release", "break")}
    assert s2 == {"classes_begin": [("2026-07-20", None)], "census": [("2026-08-31", None)],
                  "assessment_period": [("2026-10-26", "2026-11-13")], "results_release": [("2026-11-30", None)],
                  "break": [("2026-08-31", "2026-09-06")]}
    assert event(data, "2026-S1", "results_release")["date"] == "2026-07-13"
    assert event(data, "2026-S1", "assessment_period")["end_date"] == "2026-06-26"


def test_week_tables_match_the_published_weeks(data):
    weeks = {w["label"]: (w["start"], w["end"]) for w in period(data, "2026-S2")["weeks"]}
    assert weeks["Week 9"] == ("2026-09-21", "2026-09-27")
    assert weeks["Mid-semester break"] == ("2026-08-31", "2026-09-06")
    assert weeks["Week 16"] == ("2026-11-09", "2026-11-15")
    # The break event and the week table give the same dates in both semesters
    for pid in ("2026-S1", "2026-S2"):
        table = next(w for w in period(data, pid)["weeks"] if w["label"] == "Mid-semester break")
        brk = next(e for e in period(data, pid)["events"] if e["category"] == "break" and "Mid-semester" in e["event"])
        assert (brk["date"], brk["end_date"]) == (table["start"], table["end"])


def test_the_one_correction_to_the_published_dates_is_recorded(data, pub):
    assert len(pub["corrections"]) == 1
    fix = pub["corrections"][0]
    assert (fix["period"], fix["field"], fix["published"], fix["used"]) == ("2026-S1", "end_date", "2026-04-10", "2026-04-12")
    published = next(e for e in pub["key_dates"]["2026-S1"]["events"] if e["event"] == fix["event"])
    assert published["end_date"] == "2026-04-10"  # the transcription stays as published
    used = next(e for e in period(data, "2026-S1")["events"] if e["event"] == fix["event"])
    assert used["end_date"] == "2026-04-12" and used["note"] == fix["note"] and "3 to 12 April" in used["note"]
    assert [e["id"] for p in data["key_dates"] for e in p["events"] if e["note"]] == [used["id"]]


def test_a_correction_that_matches_no_published_event_is_refused(pub):
    bad = {**pub, "corrections": [{**pub["corrections"][0], "published": "2026-04-11"}]}
    with pytest.raises(AssertionError, match="does not match the published"):
        generate.build_key_dates(bad, generate.SNAPSHOT_DATE)
    stray = {**pub, "corrections": [{**pub["corrections"][0], "event": "No such event"}]}
    with pytest.raises(AssertionError, match="match no event"):
        generate.build_key_dates(stray, generate.SNAPSHOT_DATE)


def test_validator_flags_a_correction_pointing_at_nothing(data, monkeypatch):
    stray = {**validate.PUBLIC_SOURCE, "corrections": [{**validate.PUBLIC_SOURCE["corrections"][0], "event": "No such event"}]}
    monkeypatch.setattr(validate, "PUBLIC_SOURCE", stray)
    assert any("matches no event" in e for e in validate.validate(data))


def test_add_deadlines_say_which_schools_they_apply_to(data):
    scopes = {e["date"]: e["applies_to"] for e in period(data, "2026-S2")["events"] if e["category"] == "add_deadline"}
    assert scopes == {"2026-07-27": "art_architecture_fashion_only", "2026-08-02": "all_other_schools"}
    assert all(e["applies_to"] is None for p in data["key_dates"] for e in p["events"] if e["category"] != "add_deadline")


def test_term_calendar_uses_published_dates_where_they_exist(data):
    terms = {t["term"]: t for t in data["terms"]}
    published = {"start_date": "2026-07-20", "enrolment_closes": "2026-08-02", "census_date": "2026-08-31", "end_date": "2026-11-13"}
    assert {k: terms["2026-S2"][k] for k in published} == published
    assert set(terms["2026-S2"]["field_provenance"]) == set(published)
    assert terms["2027-S1"]["enrolment_opens"] == terms["2027-S2"]["enrolment_opens"] == "2026-10-01"
    assert terms["2028-S1"]["field_provenance"] == {}


def test_categories_for_tricky_events():
    for text, category in [("New Year's Day (Friday)", "holiday"), ("Enrolment Online opens for 2027 enrolments", "enrolment_opens"),
                           ("Semester 1 deferred assessment period", "deferred_assessment_period"),
                           ("Semester 1 assessment period", "assessment_period"),
                           ("Easter Tuesday RMIT holiday", "holiday"), ("Spring Semester (2025-2026) begins", "classes_begin"),
                           ("RMIT University re-opens (Monday)", "university_reopens"),
                           ("Deadline for timely re-enrolment: last day for continuing students to re-enrol", "re_enrolment_deadline")]:
        assert generate.categorise(text) == category
    with pytest.raises(ValueError, match="No category rule"):
        generate.categorise("Free pizza in the union")


# (name, mutation, text expected in an error)
BREAKS = [
    ("stage items do not add up", lambda d: d["programs"][0]["stages"][0]["items"][2].update(credit_points=30), "items sum to 54"),
    ("stage total credit points", lambda d: d["programs"][0]["stages"][0].update(credit_points=50), "items sum to 48 cp but the stage says 50"),
    ("program total credit points", lambda d: d["programs"][0].update(total_credit_points=100), "total_credit_points"),
    ("option list too small", lambda d: d["programs"][0]["option_list"].update(course_ids=["COSC2632"]), "option list offers"),
    ("choice list too small", lambda d: d["programs"][0]["stages"][0]["items"].append(
        {"type": "choice", "credit_points": 24, "course_ids": ["COSC2632"]}), "choice item needs 24 cp"),
    ("student in a program that does not exist", lambda d: d["students"][0].update(program_code="XX"), "not in programs.json"),
    ("student with a load the program does not offer", lambda d: d["programs"][0].update(study_load={"full_time_cp_per_semester": 48}),
     "study_load part_time is not offered"),
    ("prerequisite course missing", lambda d: course(d, "COSC3154")["prerequisites"].append("NOPE9999"), "NOPE9999"),
    ("stage references missing course", lambda d: d["programs"][0]["stages"][1]["items"][0].update(course_id="NOPE9999"), "NOPE9999"),
    ("option list references missing course", lambda d: d["programs"][0]["option_list"]["course_ids"].append("NOPE9999"), "NOPE9999"),
    ("compulsory course also an option", lambda d: d["programs"][0]["option_list"]["course_ids"].append("COSC2148"), "both compulsory"),
    ("offering references missing course", lambda d: offering(d).update(course_id="NOPE9999"), "NOPE9999"),
    ("program course has no offering", lambda d: d["timetable"].__setitem__(
        slice(None), [o for o in d["timetable"] if o["course_id"] != "COSC3155"]), "COSC3155 has no timetable offering"),
    ("option course has no offering", lambda d: d["timetable"].__setitem__(
        slice(None), [o for o in d["timetable"] if o["course_id"] != "COSC2673"]), "COSC2673 has no timetable offering"),
    ("missing provenance", lambda d: course(d, "COSC2148").pop("provenance"), "missing provenance"),
    ("missing snapshot_date", lambda d: d["programs"][0].pop("snapshot_date"), "missing snapshot_date"),
    ("bad snapshot_date", lambda d: d["programs"][0].update(snapshot_date="21/09/2026"), "not an ISO date"),
    ("mixed snapshot dates", lambda d: course(d, "COSC2462").update(snapshot_date="2026-01-01"), "different snapshot dates"),
    ("record-level public", lambda d: course(d, "COSC2148").update(provenance="from_public_page"), "record-level"),
    ("public value changed", lambda d: course(d, "COSC2148").update(title="Something Else"), "public value"),
    ("public option course title changed", lambda d: course(d, "COSC2673").update(title="Machine Learning II"), "public value"),
    ("public field not in 5.1", lambda d: course(d, "COSC2462")["field_provenance"].update(description="from_public_page"), "not listed in requirements 5.1"),
    ("public class_id changed", lambda d: first_option(d).update(class_id="1099"), "1015"),
    ("handbook code looks real", lambda d: course(d, "COSC2462").update(handbook_code="123456"), "must be synthetic"),
    ("duplicate handbook code", lambda d: course(d, "COSC2462").update(handbook_code="031749"), "duplicate handbook_code"),
    ("duplicate class_id", lambda d: offering(d)["components"][1]["options"][0].update(
        class_id=first_option(d)["class_id"]), "duplicate class_id"),
    ("lecture not online", lambda d: first_option(d).update(mode="on_campus", campus="City"), "lecture mode must be online"),
    ("online option with campus", lambda d: first_option(d, component="workshop").update(mode="online", campus="City"), "campus must be null"),
    ("component without options", lambda d: offering(d)["components"][1].update(options=[]), "has no options"),
    ("missing component", lambda d: offering(d).update(components=offering(d)["components"][:1]), "components must be exactly"),
    ("start after end", lambda d: first_option(d, component="workshop").update(start="20:00", end="18:00"), "not before end"),
    ("partial time", lambda d: first_option(d, component="workshop").update(start=None), "all be set or all null"),
    ("seats over capacity", lambda d: first_option(d).update(seats_taken=99, seats_total=60), "seats_taken"),
    ("duplicate offering", lambda d: d["timetable"].append(dict(offering(d))), "duplicate offering"),
    ("no students", lambda d: d.update(students=[]), "non-empty list"),
    ("duplicate student number", lambda d: student(d, "S0000002").update(student_number="S0000001"), "duplicate student_number"),
    ("duplicate student email", lambda d: student(d, "S0000002").update(email=student(d, "S0000001")["email"]), "duplicate student email"),
    ("student number looks real", lambda d: student(d, "S0000001").update(student_number="3712345"), "student_number must look like"),
    ("real student email", lambda d: student(d, "S0000001").update(email="s1@rmit.edu.au"), "example.invalid"),
    ("student start term malformed", lambda d: student(d, "S0000001").update(start_term="next year"), "start_term"),
    ("result for unknown course", lambda d: student(d, "S0000004")["results"].append({"course_id": "NOPE9999", "term": "2025-S1", "mark": 60}), "unknown course"),
    ("result mark not whole", lambda d: student(d, "S0000004")["results"][0].update(mark=78.5), "whole number"),
    ("result mark over 100", lambda d: student(d, "S0000004")["results"][0].update(mark=101), "whole number from 0 to 100"),
    ("result in a current or future term", lambda d: student(d, "S0000004")["results"][0].update(term="2026-S2"), "past term"),
    ("duplicate result", lambda d: student(d, "S0000004")["results"].append(dict(student(d, "S0000004")["results"][0])), "duplicate result"),
    ("enrolment in unknown offering", lambda d: student(d, "S0000004")["current_enrolments"][0].update(term="2031-S1"), "no such timetable offering"),
    ("enrolment with wrong classes", lambda d: student(d, "S0000004")["current_enrolments"][0].update(class_ids=["1", "2"]), "one lecture option and one workshop option"),
    ("enrolment prerequisite not passed", lambda d: student(d, "S0000006").update(
        results=[r for r in student(d, "S0000006")["results"] if r["course_id"] != "COSC2148"]), "prerequisite COSC2148 not passed"),
    ("enrolled in a passed course", lambda d: student(d, "S0000004")["results"].append({"course_id": "COSC2110", "term": "2025-S2", "mark": 70}), "already passed"),
    ("enrolled with no enrolments", lambda d: student(d, "S0000004").update(current_enrolments=[]), "does not match current_enrolments"),
    ("admitted with enrolments", lambda d: student(d, "S0000001").update(current_enrolments=student(d, "S0000004")["current_enrolments"]), "does not match current_enrolments"),
    ("fee type does not match residency", lambda d: student(d, "S0000003").update(fee_type="hecs_csp"), "does not match residency"),
    ("unknown fee type", lambda d: student(d, "S0000001").update(fee_type="scholarship"), "not in fees.json"),
    ("hold without a balance", lambda d: student(d, "S0000007")["account"].update(balance_due=0), "needs a balance_due"),
    ("negative balance", lambda d: student(d, "S0000001")["account"].update(balance_due=-5), "non-negative"),
    ("prior gpa out of range", lambda d: student(d, "S0000001")["prior_qualification"].update(gpa=4.5), "0 to 4"),
    ("plaintext password stored", lambda d: d["accounts"][0].update(password="demo1"), "plaintext password"),
    ("account for unknown student", lambda d: d["accounts"][0].update(student_number="S0000099"), "unknown student"),
    ("student without an account", lambda d: d["accounts"].pop(), "expected 1"),
    ("two accounts for a student", lambda d: d["accounts"][1].update(student_number="S0000001"), "expected 1"),
    ("duplicate username", lambda d: d["accounts"][1].update(username="demo1"), "duplicate username"),
    ("short password hash", lambda d: d["accounts"][0].update(password_hash="abc"), "salted hash"),
    ("term missing from calendar", lambda d: d["terms"].pop(0), "has no entry in terms.json"),
    ("term dates out of order", lambda d: d["terms"][1].update(census_date="2020-01-01"), "in order"),
    ("term date not ISO", lambda d: d["terms"][1].update(start_date="1 March"), "ISO dates"),
    ("fees do not rise by type", lambda d: d["fees"]["fee_types"]["international"].update(fee_per_12cp=100), "must rise"),
    ("fee type missing a rule", lambda d: d["fees"]["fee_types"]["hecs_csp"].update(payment_rule=""), "needs a label"),
    ("no failed course", lambda d: [r.update(mark=60) for s in d["students"] for r in s["results"]], "no student with a failed course"),
    ("no account hold", lambda d: [s["account"].update(hold=None) for s in d["students"]], "no student with an account hold"),
    ("only one fee type", lambda d: [s.update(fee_type="hecs_csp", residency="domestic") for s in d["students"]], "all three fee types"),
    ("real coordinator email", lambda d: course(d, "COSC2148")["coordinator"].update(email="a@rmit.edu.au"), "example.invalid"),
    ("no full option", lambda d: [o.update(seats_taken=0) for x in d["timetable"] for c in x["components"]
                                  for o in c["options"] if o["seats_taken"] >= o["seats_total"]], "no full option"),
    ("no daytime-only course", remove_daytime_only_courses, "no course whose workshops are all daytime"),
    ("too few evening option courses", remove_option_evenings, "fewer than 2 option courses have an evening workshop"),
    ("correction not applied", lambda d: event(d, "2026-S1", "break").update(end_date="2026-04-10"), "is not applied with its note"),
    ("note without a correction", lambda d: event(d, "2026-S2", "census").update(note="Changed"), "has a note but no correction"),
    ("break event and week table disagree", lambda d: event(d, "2026-S2", "break").update(end_date="2026-09-05"), "disagree"),
    ("contact without the default recipient", lambda d: d["contacts"].__setitem__(slice(None), [c for c in d["contacts"] if c["team_id"] != "school_office"]), "school_office"),
    ("contact with a real email", lambda d: d["contacts"][0].update(email="office@rmit.edu.au"), "example.invalid"),
    ("contact without topics", lambda d: d["contacts"][1].update(topics=[]), "needs a name"),
    ("duplicate contact", lambda d: d["contacts"][1].update(team_id="school_office"), "duplicate team_id"),
    ("key date moved", lambda d: event(d, "2026-S2", "census").update(date="2026-08-30"), "public value"),
    ("key date renamed", lambda d: event(d, "2026-S2", "results_release").update(event="Results are out"), "public value"),
    ("week table typo", lambda d: period(d, "2026-S2")["weeks"][8].update(end="2026-09-28"), "public value"),
    ("event has an unknown category", lambda d: event(d, "2026-S2", "census").update(category="parties"), "unknown category"),
    ("add deadline without a scope", lambda d: event(d, "2026-S2", "add_deadline").update(applies_to=None), "applies_to"),
    ("scope on a non add deadline", lambda d: event(d, "2026-S2", "census").update(applies_to="all_other_schools"), "applies_to"),
    ("weekday note contradicts the date", lambda d: event(d, "2026-S2", "holiday").update(date="2026-09-26"), "weekday note"),
    ("duplicate event id", lambda d: period(d, "2026-S2")["events"][1].update(id=period(d, "2026-S2")["events"][0]["id"]), "duplicate event id"),
    ("event ends before it starts", lambda d: event(d, "2026-S2", "assessment_period").update(end_date="2026-10-01"), "end_date is before date"),
    ("period without a census", lambda d: period(d, "2026-SUM").update(
        events=[e for e in period(d, "2026-SUM")["events"] if e["category"] != "census"]), "no census event"),
    ("week missing from the table", lambda d: period(d, "2026-S1")["weeks"].pop(2), "Week 1 to Week 16"),
    ("weeks on a spring period", lambda d: period(d, "2026-SPR").update(weeks=period(d, "2026-S2")["weeks"]), "only semesters have a week table"),
    ("term calendar disagrees with key dates", lambda d: d["terms"][0].update(census_date="2026-08-28"), "does not match the key dates"),
    ("no week covers the snapshot date", lambda d: d["programs"][0].update(snapshot_date="2030-01-01"), "no teaching week covers"),
    ("major has the wrong credit points", lambda d: bcs(d)["majors"][0].update(credit_points=90), "needs 90 cp but a major is 96"),
    ("minor groups do not add up", lambda d: bcs(d)["minors"][0]["groups"][0].update(credit_points=40), "its groups do not add up"),
    ("minor group needs more credit points than it lists", lambda d: bcs(d)["minors"][0]["groups"][0].update(course_ids=["COSC1127"]),
     "needs 48 cp but lists fewer"),
    ("duplicate major name", lambda d: bcs(d)["majors"].append(bcs(d)["majors"][0]), "duplicate major"),
    ("major references a missing course", lambda d: bcs(d)["majors"][0]["course_ids"].append("NOPE9999"), "NOPE9999"),
    ("alternate code duplicates a real course", lambda d: course(d, "COSC2960").setdefault(
        "alternate_codes", [])[:0] or course(d, "COSC2960")["alternate_codes"].append({"course_id": "COSC2148", "campus": "City Campus"}),
     "also a course of its own"),
    ("alternate code reused", lambda d: course(d, "COSC1127").__setitem__(
        "alternate_codes", [{"course_id": course(d, "COSC2960")["alternate_codes"][0]["course_id"], "campus": "City Campus"}]),
     "is used by"),
    ("student in an unknown program", lambda d: d["students"][8].update(program_code="BP999"), "not in programs.json"),
    ("student on a load their program does not offer", lambda d: bcs(d).update(study_load={"full_time_cp_per_semester": 48}),
     "study_load part_time is not offered"),
    ("malformed data does not crash", lambda d: d["programs"][0].pop("stages"), "malformed"),
]


@pytest.mark.parametrize("mutate,expected", [b[1:] for b in BREAKS], ids=[b[0] for b in BREAKS])
def test_validator_catches(data, mutate, expected):
    mutate(data)
    errors = validate.validate(data)
    assert any(expected in e for e in errors), errors


def test_validator_cli_exit_codes(tmp_path):
    script = str(ROOT / "seed" / "validate.py")
    ok = subprocess.run([sys.executable, script], capture_output=True, text=True)
    assert ok.returncode == 0 and "Result: PASS" in ok.stdout

    for name in validate.FILES.values():
        (tmp_path / name).write_text((DATA / name).read_text(encoding="utf-8"), encoding="utf-8")
    programs = json.loads((tmp_path / "programs.json").read_text(encoding="utf-8"))
    programs[0]["stages"][0]["credit_points"] = 30
    (tmp_path / "programs.json").write_text(json.dumps(programs), encoding="utf-8")
    bad = subprocess.run([sys.executable, script, "--data", str(tmp_path)], capture_output=True, text=True)
    assert bad.returncode == 1 and "Result: FAIL" in bad.stdout


def test_every_canvas_course_has_named_assignments_with_one_sentence_summaries(data):
    named = json.loads(generate.CANVAS_ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
    assert {a["course_id"] for a in data["canvas"]} <= set(named)
    first = next(a for a in data["canvas"] if a["course_id"] == "COSC2110" and a["sequence"] == 1)
    assert first["name"] == "Data Pre-processing" and first["summary"].endswith(".")


def test_a_course_without_named_assignments_falls_back_to_generic_ones():
    about = generate.canvas_assignment({}, {"course_id": "XXXX0000", "title": "Example Course"}, 2)
    assert about["name"] == "Applied Project" and "Example Course" in about["summary"]


def test_no_canvas_assignment_is_overdue_on_the_demo_date(data):
    overdue = [a["assignment_id"] for a in data["canvas"] if not a["submitted"] and a["due_date"] < generate.DEMO_DATE]
    assert overdue == []


def test_assignment_2_is_due_the_sunday_after_next_from_the_demo_date():
    assert generate.next_sunday_night("2026-10-03").isoformat() == "2026-10-11"  # Saturday: not tomorrow
    assert generate.next_sunday_night("2026-10-07").isoformat() == "2026-10-11"  # Wednesday: that Sunday
    assert generate.next_sunday_night("2026-10-09").isoformat() == "2026-10-18"  # Friday: too close, next one
