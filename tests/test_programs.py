from tools import planning, programs as prog
from tools.common import load

COURSES = {c: {"credit_points": cp} for c, cp in {"A1": 12, "A2": 24, "C1": 12, "C2": 12, "C3": 12, "O1": 12, "O2": 12, "O3": 12, "S1": 6, "S2": 6}.items()}

PROGRAM = {
    "program_code": "T1", "study_load": {"full_time_cp_per_semester": 48, "part_time_cp_per_semester": 24},
    "option_list": {"title": "Options", "course_ids": ["O1", "O2", "O3", "C1", "S1", "S2"]},
    "stages": [
        {"stage": "Y1", "ordered": True, "items": [{"type": "course", "course_id": "A1"}, {"type": "course", "course_id": "A2"},
                                                 {"type": "options", "credit_points": 24}]},
        {"stage": "Y2", "items": [{"type": "choice", "credit_points": 12, "course_ids": ["C1", "C2", "C3"]},
                                 {"type": "course", "course_id": "A1x"}, {"type": "options", "credit_points": 12}]},
    ],
}


def sequence(done=()):
    courses = {**COURSES, "A1x": {"credit_points": 12}}
    return planning.build_sequence(PROGRAM, courses, set(done))


def test_the_program_is_walked_in_order_with_fixed_courses_and_slots():
    assert sequence() == [
        ("compulsory", "A1"), ("compulsory", "A2"), ("option", ["O1", "O2", "O3", "C1", "S1", "S2"], "options", 24),
        ("option", ["C1", "C2", "C3"], "choice", 12), ("compulsory", "A1x"),
        ("option", ["O1", "O2", "O3", "C1", "S1", "S2"], "options", 12)]


def test_courses_already_done_are_left_out_and_count_towards_the_first_slots():
    assert ("compulsory", "A1") not in sequence(done={"A1"})
    filled = sequence(done={"O1", "O2"})          # two 12 cp options fill the 24 cp item in stage Y1
    assert [s for s in filled if s[0] == "option" and s[2] == "options"] == [
        ("option", ["O1", "O2", "O3", "C1", "S1", "S2"], "options", 12)]
    part = sequence(done={"O1"})
    assert part[2][3] == 12                        # 12 cp of the 24 cp are still to place


def test_a_course_done_from_a_choice_list_satisfies_it():
    assert all(s[2] != "choice" for s in sequence(done={"C2"}) if s[0] == "option")


def test_a_course_counts_once_towards_the_first_item_it_can_fill():
    slots = [s[3] for s in sequence(done={"C1"}) if s[0] == "option"]
    assert slots == [12, 12, 12]   # C1 fills 12 of the 24 cp in Y1, so the choice and the Y2 options are still to do


def test_six_credit_point_courses_reduce_what_is_needed_by_six():
    left = sequence(done={"S1"})
    assert left[2][3] == 18


def test_helpers_read_the_stages_and_items():
    assert prog.course_ids(PROGRAM["stages"][0]) == ["A1", "A2"]
    assert prog.stage_of(PROGRAM) == {"A1": "Y1", "A2": "Y1", "A1x": "Y2"}
    assert prog.order_before(PROGRAM) == {"A1": None, "A2": "A1", "A1x": None}   # only ordered stages chain
    assert prog.option_credit_points(PROGRAM["stages"][0]) == 24 and prog.choice_credit_points(PROGRAM["stages"][1]) == 12
    assert prog.free_credit_points(PROGRAM) == 48
    assert prog.pool(PROGRAM, PROGRAM["stages"][1]["items"][0]) == ["C1", "C2", "C3"]
    assert prog.pool(PROGRAM, PROGRAM["stages"][0]["items"][2]) == PROGRAM["option_list"]["course_ids"]
    assert prog.study_load_label(PROGRAM, 24) == "part-time" and prog.study_load_label(PROGRAM, 36) is None
    assert prog.credit_per_semester(PROGRAM, "full_time") == 48 and prog.credit_per_semester(PROGRAM, "night") is None


def test_programs_are_found_by_code_ignoring_case_and_students_get_their_own():
    assert prog.get_program(" bh013p26 ")["program_code"] == "BH013P26"
    assert prog.get_program("XX") is None and prog.get_program(None) is None
    student = load("students.json")[0]
    assert prog.program_for(student)["program_code"] == student["program_code"]
    r = prog.unknown_program("XX")
    assert r["found"] is False and "BH013P26" in r["reason"]
