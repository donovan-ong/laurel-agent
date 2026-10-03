import json

import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import common
from tools.course_tools import find_courses, lookup_course
from tools.program_tools import lookup_program


CTX = AgentRun(request_context={"student_number": "S0000001"})


def program():
    return lookup_program.fn(context=CTX)


def course(query):
    return lookup_course.fn(context=CTX, query=query)


def test_program_structure_matches_the_data():
    r = program()
    p = r["program"]
    assert r["found"] and (p["program_code"], p["total_credit_points"], p["campus"]) == ("BH013P26", 96, "Melbourne City")
    assert p["title"] == "Bachelor of Computer Science (Honours)"
    assert p["duration"] == {"full_time_years": 1, "part_time_years": 2}
    assert [(s["stage"], s["credit_points"], s["compulsory_credit_points"], s["option_credit_points"]) for s in p["stages"]] == [
        ("A", 48, 24, 24), ("B", 48, 36, 12)]
    assert [[c["course_id"] for c in s["compulsory_courses"]] for s in p["stages"]] == [
        ["COSC2148", "COSC2462"], ["COSC3154", "COSC3155"]]
    assert p["stages"][0]["compulsory_courses"][1] == {
        "course_id": "COSC2462", "title": "Preliminary Computer Science Honours Thesis", "credit_points": 12}
    assert p["stages"][0]["note"].startswith("Students must complete a series of compulsory onboarding modules")
    assert len(p["option_list"]["courses"]) == 21 and p["option_list"]["title"] == "Computer Science Honours Option List"
    assert p["intakes"] == ["February", "July"]


def test_program_semesters_come_from_credit_points_and_load():
    p = program()["program"]
    assert p["study_load"] == {"full_time_cp_per_semester": 48, "part_time_cp_per_semester": 24}
    assert p["minimum_semesters"]["full_time"] == 2 and p["minimum_semesters"]["part_time"] == 4


def test_program_says_what_is_published_and_the_source_is_mixed():
    r = program()
    assert {"program_code", "title", "duration", "stages"} <= set(r["published_fields"])
    assert "study_load" not in r["published_fields"] and "total_credit_points" not in r["published_fields"]
    assert r["source"] == {"provenance": "mixed", "snapshot_date": "2026-09-21", "file": "programs.json"}


@pytest.mark.parametrize("code", [None, "", "bh013p26", " BH013P26 "])
def test_program_code_defaults_and_ignores_case(code):
    assert lookup_program.fn(context=CTX, program_code=code)["found"] is True


def test_another_program_is_not_found():
    r = lookup_program.fn(context=CTX, program_code="BP094")
    assert r["found"] is False and "no data for program BP094" in r["reason"] and "BH013P26" in r["reason"]


# Course lookup

def test_code_handbook_code_and_title_return_the_same_record():
    by_code, by_handbook, by_title = course("COSC2148"), course("031749"), course("Computing Research and Project Preparation")
    assert by_code["course"] == by_handbook["course"] == by_title["course"]
    assert [r["matched_by"] for r in (by_code, by_handbook, by_title)] == ["course code", "Handbook code", "title"]
    c = by_code["course"]
    assert (c["title"], c["credit_points"], c["handbook_code"], c["campus"]) == (
        "Computing Research and Project Preparation", 12, "031749", "City Campus")
    assert c["delivery_modes"] == ["hybrid_blended", "online", "distance"] and c["assumed_knowledge"] == []


@pytest.mark.parametrize("query", ["cosc2148", "  COSC2148 ", "computing RESEARCH and project   preparation"])
def test_matching_ignores_case_and_spacing(query):
    assert course(query)["course"]["course_id"] == "COSC2148"


def test_a_partial_title_that_names_one_course_finds_it():
    r = course("machine learning")
    assert r["found"] and r["course"]["course_id"] == "COSC2673"
    assert course("autonomous robots")["course"]["course_id"] == "COSC2814"
    assert course("human centered")["course"]["course_id"] == "INTE2696"  # the title has a hyphen


@pytest.mark.parametrize("query,expected", [
    ("thesis", ["COSC2462", "COSC3154", "COSC3155"]),
    ("big data", ["COSC2632", "COSC2633", "LAW2604"]),
    ("learning", ["COSC2972", "COSC2673", "EMPL1008"]),
])
def test_ambiguous_queries_list_candidates_and_do_not_guess(query, expected):
    r = course(query)
    assert r["found"] is False and r["ambiguous"] is True
    assert [c["course_id"] for c in r["candidates"]] == expected
    assert "Ask the student which one" in r["reason"] and "course" not in r
    assert all({"course_id", "title", "credit_points"} == set(c) for c in r["candidates"])


@pytest.mark.parametrize("query", ["zzz", "", "   ", "COSC9999"])
def test_unknown_queries_are_not_found(query):
    r = course(query)
    assert r["found"] is False and "ambiguous" not in r and "no course matching" in r["reason"]


def test_a_common_word_matches_several_courses_and_is_reported_as_ambiguous():
    r = course("the")
    assert r["found"] is False and r["ambiguous"] is True and len(r["candidates"]) >= 2


@pytest.mark.parametrize("query,expected", [
    ("Thesis Part A", "COSC3154"), ("thesis part b", "COSC3155"), ("Honours Thesis Part A", "COSC3154"),
    ("part a", "COSC3154"), ("Preliminary Computer Science Honours Thesis", "COSC2462"), ("machine learn", "COSC2673"),
])
def test_a_phrase_with_a_short_word_finds_the_one_course_it_names(query, expected):
    r = course(query)
    assert r["found"] and r["course"]["course_id"] == expected, r


def test_a_phrase_shared_by_two_courses_is_still_ambiguous():
    assert [c["course_id"] for c in course("thesis part")["candidates"]] == ["COSC3154", "COSC3155"]
    assert [c["course_id"] for c in course("honours thesis")["candidates"]] == ["COSC2462", "COSC3154", "COSC3155"]


def test_a_word_inside_another_word_is_not_a_phrase_match():
    assert course("the")["found"] is False and course("sis")["found"] is False


def test_missing_details_are_reported_as_missing():
    c = course("COSC3047")["course"]
    assert c["coordinator"] is None and c["assumed_knowledge"] is None
    assert c["missing_details"] == ["assumed_knowledge", "coordinator"]
    assert course("COSC2148")["course"]["missing_details"] == []
    assert course("COSC2462")["course"]["missing_details"] == ["assumed_knowledge"]


def test_only_cosc2148_has_a_real_description_and_handbook_code():
    real = course("COSC2148")["course"]
    assert real["description_is_placeholder"] is False and real["handbook_code_is_synthetic"] is False
    assert real["description"].startswith("This course focuses on research techniques")
    other = course("COSC2462")["course"]
    assert other["description_is_placeholder"] is True and other["handbook_code_is_synthetic"] is True
    assert other["handbook_code"].startswith("S") and "placeholder" in other["description"].lower()


def test_prerequisites_are_named():
    c = course("COSC3155")["course"]
    assert c["prerequisites"] == [
        {"course_id": "COSC2148", "title": "Computing Research and Project Preparation"},
        {"course_id": "COSC2462", "title": "Preliminary Computer Science Honours Thesis"}]
    assert course("COSC2148")["course"]["prerequisites"] == []


def test_role_in_the_program():
    assert course("COSC2148")["course"]["role_in_program"]["kind"] == "compulsory" and course("COSC2148")["course"]["role_in_program"]["stage"] == "A"
    assert course("COSC3155")["course"]["role_in_program"]["stage"] == "B"
    option = course("COSC2110")["course"]["role_in_program"]
    assert option["kind"] == "option" and option["option_list"] == "Computer Science Honours Option List"
    assert "24 cp of options in Stage A" in option["note"] and "12 cp of options in Stage B" in option["note"]
    assert option["program_code"] == "BH013P26"
    assert course("COSC2148")["course"]["role_in_programs"] == [{"kind": "compulsory", "stage": "A", "program_code": "BH013P26",
                                                                "program": "Bachelor of Computer Science (Honours)"}]


def test_offered_terms_follow_the_timetable():
    from tools import scheduling as sch
    assert course("COSC2148")["course"]["offered_terms"] == sch.offered_terms("COSC2148")
    assert course("Data Mining")["course"]["offered_terms"] == sch.offered_terms("COSC2110")
    assert course("Big Data Management")["course"]["offered_terms"] == sch.offered_terms("COSC2632")


def test_course_source_and_published_fields():
    r = course("COSC2148")
    assert r["source"] == {"provenance": "mixed", "snapshot_date": "2026-09-21", "file": "courses.json"}
    assert {"course_id", "title", "credit_points", "campus", "handbook_code", "description"} <= set(r["published_fields"])
    assert set(course("COSC2462")["published_fields"]) == {"course_id", "title", "credit_points", "campus"}


def test_every_course_can_be_found_by_its_code_title_and_handbook_code():
    for c in common.load("courses.json"):
        for query in (c["course_id"], c["handbook_code"], c["title"]):
            r = lookup_course.fn(context=CTX, query=query)
            assert r["found"] and r["course"]["course_id"] == c["course_id"], query


def test_the_tools_take_no_student_and_are_read_only():
    for t in (lookup_program, lookup_course):
        props = set(t.__tool_spec__.input_schema.properties or {})
        assert props <= {"context", "program_code", "query"} and not props & {"student_number", "student_id"}
        assert t.__tool_spec__.permission.value == "read_only"


def test_find_courses_prefers_an_exact_code_over_word_matches():
    courses = common.load("courses.json")
    assert [c["course_id"] for c in find_courses("COSC2110", courses)[0]] == ["COSC2110"]
    assert find_courses("", courses) == ([], None)


def test_results_are_json_serialisable():
    json.dumps(program()), json.dumps(course("COSC2148")), json.dumps(course("thesis"))
