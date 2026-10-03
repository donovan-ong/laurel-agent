"""Programs and their structure. A program is a list of stages, and a stage is an ordered list of items:

  course   a fixed course
  options  credit points from the program's option pool (`option_list`)
  choice   credit points from a short list given on the item (`course_ids`)

Callers must not modify what these functions return.
"""
from tools.common import load, not_found


def all_programs() -> list[dict]:
    return load("programs.json")


def get_program(code: str | None) -> dict | None:
    code = (code or "").strip().upper()
    return next((p for p in all_programs() if p["program_code"] == code), None)


def program_for(student: dict) -> dict:
    """The program the student is enrolled in."""
    return get_program(student["program_code"])


def unknown_program(code: str | None) -> dict:
    known = ", ".join(p["program_code"] for p in all_programs())
    return not_found(f"There is no data for program {code}. Programs with data: {known}.")


def items(program: dict):
    """(stage, item) for every item of every stage, in order."""
    return [(s, i) for s in program["stages"] for i in s["items"]]


def course_ids(stage: dict) -> list[str]:
    return [i["course_id"] for i in stage["items"] if i["type"] == "course"]


def compulsory_ids(program: dict) -> list[str]:
    return [c for s in program["stages"] for c in course_ids(s)]


def stage_of(program: dict) -> dict[str, str]:
    return {c: s["stage"] for s in program["stages"] for c in course_ids(s)}


def order_before(program: dict) -> dict[str, str | None]:
    """For each compulsory course, the course that must come before it, in stages marked ordered."""
    before = {}
    for s in program["stages"]:
        for n, c in enumerate(course_ids(s)):
            before[c] = course_ids(s)[n - 1] if n and s.get("ordered") else None
    return before


def option_credit_points(stage: dict) -> int:
    """Credit points a stage takes from the option pool."""
    return sum(i["credit_points"] for i in stage["items"] if i["type"] == "options")


def choice_credit_points(stage: dict) -> int:
    """Credit points a stage takes from short lists of courses (a choice of one)."""
    return sum(i["credit_points"] for i in stage["items"] if i["type"] == "choice")


def free_credit_points(program: dict) -> int:
    """Credit points across the program that are not fixed courses."""
    return sum(option_credit_points(s) + choice_credit_points(s) for s in program["stages"])


def compulsory_credit_points(stage: dict, credit_points: dict) -> int:
    return sum(credit_points[c] for c in course_ids(stage))


def pool(program: dict, item: dict) -> list[str]:
    """The courses an options or choice item may be filled from."""
    return list(item.get("course_ids") or program["option_list"]["course_ids"])


def option_pool(program: dict) -> list[str]:
    return list(program["option_list"]["course_ids"])


def study_load_label(program: dict, cap: int) -> str | None:
    for key, value in program["study_load"].items():
        if value == cap:
            return key.split("_cp_")[0].replace("_", "-")
    return None


def credit_per_semester(program: dict, load_name: str) -> int | None:
    return program["study_load"].get(f"{load_name}_cp_per_semester")


def excluded_from_majors_minors(program: dict) -> set[str]:
    """Courses that count as core (compulsory or a choice item) and so cannot also count towards a major or minor."""
    return set(compulsory_ids(program)) | {c for s in program["stages"] for i in s["items"] if i["type"] == "choice" for c in i["course_ids"]}


def find_named(program: dict, query: str, kind: str | None = None):
    """The majors and/or minors matching a name, and how many matched, for the caller to handle ambiguity.

    kind is "major", "minor" or None for either. Exact (case-insensitive) match wins outright; otherwise every
    one whose name contains the query, or vice versa, is returned.
    """
    from tools.common import normalise
    q = normalise(query)
    candidates = [(k, m) for k in ("major", "minor") if kind in (None, k)
                  for m in program.get(f"{k}s", [])]
    exact = [(k, m) for k, m in candidates if normalise(m["name"]) == q]
    if exact:
        return exact
    return [(k, m) for k, m in candidates if q in normalise(m["name"]) or normalise(m["name"]) in q]
