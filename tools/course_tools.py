from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog
from tools.common import current_student, find_courses, load, normalise, not_found, source


def role_in(program: dict, course_id: str) -> dict | None:
    """What a course is in one program: compulsory, a choice of one, or an option. None if it is not in the program.

    Courses that are also in a major or minor say so in part_of."""
    stage = prog.stage_of(program).get(course_id)
    if stage:
        role = {"kind": "compulsory", "stage": stage}
    else:
        choice = next((s["stage"] for s in program["stages"] for i in s["items"]
                       if i["type"] == "choice" and course_id in i["course_ids"]), None)
        if choice:
            role = {"kind": "choice", "stage": choice,
                    "note": f"One of a short list of courses in stage {choice}. The student chooses one."}
        elif course_id in program["option_list"]["course_ids"]:
            slots = [f"the {prog.option_credit_points(s)} cp of options in Stage {s['stage']}"
                     for s in program["stages"] if prog.option_credit_points(s)]
            role = {"kind": "option", "option_list": program["option_list"]["title"],
                    "note": "Counts towards " + " or ".join(slots) + "."}
        else:
            return None
    part_of = [f"{m['name']} {kind}" for kind, key in (("major", "majors"), ("minor", "minors"))
               for m in program.get(key, []) if course_id in m["course_ids"]]
    return {**role, "program_code": program["program_code"], "program": program["title"], **({"part_of": part_of} if part_of else {})}


@tool(permission=ToolPermission.READ_ONLY)
def lookup_course(context: AgentRun, query: str) -> dict:
    """Look up one course by its title, course (timetable) code such as COSC2148, or Handbook code such as 031749, and get its full record: credit points, description, delivery modes, assumed knowledge, prerequisites, coordinator, its role in the program and the terms it is offered.

    Use this for any question about a specific course. A partial title works. If the query matches several courses, found is false and candidates lists them, so ask the student which one they mean and do not guess. missing_details lists what the data does not have, so say so and do not invent it. description_is_placeholder means there is no real Handbook description.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        query: The course title (or part of it), course code or Handbook code.

    Returns:
        found and the course record with published_fields and a source block, or found false with a reason. When ambiguous, ambiguous is true and candidates lists the matching courses.
    """
    courses = load("courses.json")
    matches, how = find_courses(query or "", courses)
    if not matches:
        return not_found(f"There is no course matching {query!r}.")
    if len(matches) > 1:
        return {"found": False, "ambiguous": True,
                "reason": f"{len(matches)} courses match {query!r}. Ask the student which one they mean.",
                "candidates": [{"course_id": c["course_id"], "title": c["title"], "credit_points": c["credit_points"]}
                               for c in matches[:12]]}
    course = matches[0]
    titles = {c["course_id"]: c["title"] for c in courses}
    student, _ = current_student(context)
    own = prog.program_for(student) if student else None
    roles = [r for r in (role_in(p, course["course_id"]) for p in prog.all_programs()) if r]
    role = role_in(own, course["course_id"]) if own else None
    published = list(course["field_provenance"])
    record = {
        "course_id": course["course_id"],
        "handbook_code": course["handbook_code"],
        "handbook_code_is_synthetic": "handbook_code" not in published,
        "title": course["title"],
        "credit_points": course["credit_points"],
        "campus": course["campus"],
        "description": course["description"],
        "description_is_placeholder": "description" not in published,
        "delivery_modes": course["delivery_modes"],
        "assumed_knowledge": course["assumed_knowledge"],
        "prerequisites": [{"course_id": p, "title": titles[p]} for p in course["prerequisites"]],
        "coordinator": course["coordinator"],
        "missing_details": [f for f in ("assumed_knowledge", "coordinator") if course[f] is None],
        "role_in_program": role,
        "role_in_programs": roles,
        "offered_terms": sorted(o["term"] for o in load("timetable.json") if o["course_id"] == course["course_id"]),
    }
    return {"found": True, "matched_by": how, "course": record, "published_fields": published,
            "source": source(course, "courses.json")}
