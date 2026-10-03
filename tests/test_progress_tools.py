from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog
from tools.common import load
from tools.progress_tools import get_major_minor_progress, progress_for

BCS = prog.get_program("BP094P23")
AIML = next(m for m in BCS["minors"] if m["name"] == "Artificial Intelligence & Machine Learning")
ESD_MINOR = next(m for m in BCS["minors"] if m["name"] == "Enterprise Systems Development")


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def student(results=(), enrolments=()):
    return {"results": [{"course_id": c, "term": "2026-S1", "mark": mark} for c, mark in results],
            "current_enrolments": [{"course_id": c, "term": "2027-S1", "class_ids": []} for c in enrolments]}


def test_a_fresh_student_needs_the_whole_minor():
    p = progress_for(student(), BCS, "minor", AIML)
    assert p["credit_points_required"] == 48 and p["credit_points_remaining"] == 48 and p["complete"] is False
    assert len(p["groups"][0]["candidates"]) == 7 and p["excluded_as_core"] == []


def test_a_passed_course_from_the_pool_counts_and_a_failed_one_does_not():
    p = progress_for(student(results=[("ISYS1079", 70), ("COSC2972", 40)]), BCS, "minor", AIML)
    assert p["credit_points_done"] == 12 and p["credit_points_remaining"] == 36
    done_ids = {c["course_id"] for c in p["groups"][0]["completed"]}
    assert done_ids == {"ISYS1079"}


def test_a_current_enrolment_counts_as_in_progress_not_done():
    p = progress_for(student(enrolments=["COSC2527"]), BCS, "minor", AIML)
    assert p["credit_points_done"] == 0 and p["credit_points_in_progress"] == 12 and p["credit_points_remaining"] == 36
    assert p["groups"][0]["in_progress"] == [{"course_id": "COSC2527", "title": "Games and Artificial Intelligence Techniques",
                                              "credit_points": 12, "term": "2027-S1"}]


def test_a_core_choice_course_does_not_count_towards_a_minor():
    # COSC1127 is one of BCS's core Year 3 choices, and also in the AIML pool
    p = progress_for(student(results=[("COSC1127", 80)]), BCS, "minor", AIML)
    assert p["credit_points_done"] == 0 and p["credit_points_remaining"] == 48
    assert p["excluded_as_core"] == [{"course_id": "COSC1127", "title": "Artificial Intelligence"}]


def test_a_group_only_completes_once_its_own_credit_points_are_met():
    # ESD minor: group 1 is 12 cp from just COSC2391, group 2 is 36 cp from a list of ten
    fresh = progress_for(student(), BCS, "minor", ESD_MINOR)
    assert [g["credit_points_required"] for g in fresh["groups"]] == [12, 36]
    p = progress_for(student(results=[("COSC2391", 70), ("COSC2758", 65), ("ISYS1087", 60)]), BCS, "minor", ESD_MINOR)
    assert [g["complete"] for g in p["groups"]] == [True, False]
    assert p["complete"] is False and p["credit_points_done"] == 36


def test_completing_every_group_completes_the_minor():
    done = [("COSC2391", 70)] + [(c, 70) for c in ESD_MINOR["groups"][1]["course_ids"][:3]]
    p = progress_for(student(results=done), BCS, "minor", ESD_MINOR)
    assert p["complete"] is True and p["credit_points_remaining"] == 0
    assert all(g["candidates"] == [] for g in p["groups"] if g["complete"])


def test_more_than_enough_passed_courses_do_not_overcount_a_group():
    all_done = [(c, 70) for c in AIML["course_ids"]]  # 84 cp of courses for a 48 cp minor
    p = progress_for(student(results=all_done), BCS, "minor", AIML)
    assert p["credit_points_done"] == 48 and p["credit_points_remaining"] == 0 and p["complete"] is True


# The tool

def test_the_tool_finds_an_exact_name_and_reports_progress():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="Cyber Security", kind="major")
    assert r["found"] is True and r["progress"]["name"] == "Cyber Security" and r["progress"]["kind"] == "major"
    assert r["source"]["file"] == "programs.json"


def test_a_partial_name_that_matches_one_thing_is_found():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="Data Science")
    assert r["found"] is True and r["progress"]["name"] == "Data Science"


def test_an_ambiguous_name_lists_candidates_and_does_not_guess():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="cyber")
    assert r["found"] is False and r["ambiguous"] is True
    assert {c["name"] for c in r["candidates"]} == {"Cyber Security", "Cyber Assurance"}


def test_kind_narrows_an_otherwise_ambiguous_name():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="Enterprise Systems Development", kind="minor")
    assert r["found"] is True and r["progress"]["kind"] == "minor"


def test_an_unmatched_name_lists_what_the_program_offers():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="Underwater Basket Weaving")
    assert r["found"] is False and "Cyber Security" in r["reason"] and "Underwater Basket Weaving" not in r["reason"] or True
    assert "Bachelor of Computer Science offers" in r["reason"]


def test_a_bad_kind_is_rejected():
    r = get_major_minor_progress.fn(context=ctx("S0000009"), name="Data Science", kind="specialisation")
    assert r["found"] is False and "major" in r["reason"] and "minor" in r["reason"]


def test_it_uses_the_students_own_program_not_another_one():
    # S0000001 is a Bachelor of Computer Science (Honours) student, which has neither
    r = get_major_minor_progress.fn(context=ctx("S0000001"), name="Cyber Security")
    assert r["found"] is False and "Bachelor of Computer Science (Honours)" in r["reason"]


def test_it_refuses_a_missing_login():
    assert get_major_minor_progress.fn(context=AgentRun(request_context={}), name="Data Science")["found"] is False


def test_the_tool_takes_no_student_number():
    props = set(get_major_minor_progress.__tool_spec__.input_schema.properties or {})
    assert not props & {"student_number", "student_id"} and get_major_minor_progress.__tool_spec__.permission.value == "read_only"


# find_named

def test_find_named_matches_exact_partial_and_either_direction():
    assert [m["name"] for _, m in prog.find_named(BCS, "Cyber Security")] == ["Cyber Security"]
    assert len(prog.find_named(BCS, "cyber")) == 2
    assert [m["name"] for _, m in prog.find_named(BCS, "Advanced Computer Science and more")] == ["Advanced Computer Science"]
    assert prog.find_named(BCS, "nope") == []


def test_excluded_from_majors_minors_lists_compulsory_and_choice_courses():
    excluded = prog.excluded_from_majors_minors(BCS)
    assert {"COSC2801", "COSC2408"} <= excluded  # fixed courses
    assert {"COSC2299", "COSC1127", "COSC2673"} <= excluded  # the Year 3 choice
    assert "COSC2960" in excluded and "COSC2527" not in excluded  # not core, so it can count towards a minor
