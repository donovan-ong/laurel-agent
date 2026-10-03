from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog
from tools.common import current_student, load, not_found, source

PASS_MARK = 50


def group_progress(group: dict, courses: dict, passed: set, in_progress: dict, excluded: set) -> dict:
    """One credit-point group of a major or minor: what is done, in progress, and still to choose."""
    done = [c for c in group["course_ids"] if c in passed and c not in excluded]
    doing = [c for c in group["course_ids"] if c in in_progress and c not in excluded]
    done_cp = sum(courses[c]["credit_points"] for c in done)
    doing_cp = sum(courses[c]["credit_points"] for c in doing)
    remaining_cp = max(0, group["credit_points"] - done_cp - doing_cp)
    candidates = [c for c in group["course_ids"] if c not in done and c not in doing]

    def brief(c):
        return {"course_id": c, "title": courses[c]["title"], "credit_points": courses[c]["credit_points"]}
    return {
        "credit_points_required": group["credit_points"],
        "completed": [brief(c) for c in done], "completed_credit_points": min(done_cp, group["credit_points"]),
        "in_progress": [{**brief(c), "term": in_progress[c]} for c in doing],
        "remaining_credit_points": remaining_cp,
        "candidates": [brief(c) for c in candidates] if remaining_cp else [],
        "complete": remaining_cp == 0,
    }


def progress_for(student: dict, program: dict, kind: str, major_or_minor: dict, service_state=None) -> dict:
    courses = {c["course_id"]: c for c in load("courses.json")}
    passed = {r["course_id"] for r in student["results"] if r["mark"] >= PASS_MARK}
    enrolments = student["current_enrolments"] if service_state is None else service_state
    in_progress = {e["course_id"]: e["term"] for e in enrolments}
    excluded = prog.excluded_from_majors_minors(program)
    groups = [group_progress(g, courses, passed, in_progress, excluded) for g in major_or_minor["groups"]]
    excluded_here = [c for c in major_or_minor["course_ids"] if c in excluded and (c in passed or c in in_progress)]
    return {
        "name": major_or_minor["name"], "kind": kind, "program_code": program["program_code"],
        "credit_points_required": major_or_minor["credit_points"],
        "credit_points_done": sum(g["completed_credit_points"] for g in groups),
        "credit_points_in_progress": sum(sum(courses[c["course_id"]]["credit_points"] for c in g["in_progress"]) for g in groups),
        "credit_points_remaining": sum(g["remaining_credit_points"] for g in groups),
        "complete": all(g["complete"] for g in groups),
        "groups": groups,
        "note": major_or_minor.get("note"),
        "cross_disciplinary": major_or_minor.get("cross_disciplinary", False),
        "excluded_as_core": [{"course_id": c, "title": courses[c]["title"]} for c in excluded_here],
    }


@tool(permission=ToolPermission.READ_ONLY)
def get_major_minor_progress(context: AgentRun, name: str, kind: Optional[str] = None) -> dict:
    """Check what the logged-in student still needs to complete one major or minor of their own program, from their passed results and current enrolments.

    Use this when the student asks what they need for a specific major or minor, or how much of one they have done. Majors and minors are optional: nothing is chosen or recorded in advance, so give the name of the one they are asking about. If several majors or minors match the name, found is false and candidates lists them, so ask which one they mean. A course already used for one of the student's core (compulsory or choice) requirements does not count towards a major or minor, and excluded_as_core lists any of theirs that this affects. To see every major and minor a program offers, use lookup_program.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        name: The major or minor's name, or part of it, for example "Cyber Security" or "Data Science".
        kind: Optional "major" or "minor" if the name alone is ambiguous between the two. Leave empty otherwise.

    Returns:
        found, and for the named major or minor: its total credit points, credit points done, in progress and
        remaining, whether it is complete, each group with its completed, in-progress and candidate courses, any
        note (such as a course everyone must include), and a source block. If nobody is logged in, found is
        false. If the name matches several or none, found is false with candidates or a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    if kind not in (None, "major", "minor"):
        return not_found('kind must be "major" or "minor".')
    program = prog.program_for(student)
    matches = prog.find_named(program, name, kind)
    if not matches:
        available = [m["name"] for k in ("major", "minor") for m in program.get(f"{k}s", [])]
        return not_found(f"There is no major or minor matching {name!r} in {program['title']}. "
                         f"{program['title']} offers: {', '.join(available)}.")
    if len(matches) > 1:
        return {"found": False, "ambiguous": True,
                "reason": f"{len(matches)} of {program['title']}'s majors and minors match {name!r}. Ask the student which one they mean.",
                "candidates": [{"kind": k, "name": m["name"], "credit_points": m["credit_points"]} for k, m in matches]}
    matched_kind, major_or_minor = matches[0]
    return {"found": True, "progress": progress_for(student, program, matched_kind, major_or_minor),
            "source": source(program, "programs.json")}
