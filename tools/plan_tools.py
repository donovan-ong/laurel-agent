from typing import List, Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import planning, programs as prog, scheduling as sch
from tools.common import current_student, find_courses, load, not_found, source


@tool(permission=ToolPermission.READ_ONLY)
def build_plan(context: AgentRun, availability: Optional[dict] = None, credit_points_per_semester: Optional[int] = None,
               start_term: Optional[str] = None, preferred_option_ids: Optional[List[str]] = None) -> dict:
    """Build a semester-by-semester study plan for the logged-in student covering every course they still need, with suggested option courses and workshop times that avoid the times they cannot attend.

    Use this when the student asks whether they can finish the program, what their semesters would look like, how long it will take, or wants the plan changed. It uses their results and current enrolments, so courses already passed or in progress are not planned again (in-progress courses are assumed passed). If the student has already said when they are busy, use it; otherwise leave availability empty rather than asking first - the plan assumes no time constraints and says so in availability_used, and can be rebuilt for free once real constraints are known. Load defaults to their profile: 24 credit points a semester part-time or 48 full-time. Pass credit_points_per_semester to see the plan at another load, start_term to start later, and preferred_option_ids to choose option courses. Option courses in the plan are suggestions the student can swap. Workshops with no fixed time (the thesis) are flagged unconfirmed. The plan says how many semesters it takes and whether that matches the published duration.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        availability: The times the student cannot attend, as a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}. Leave empty for no limits.
        credit_points_per_semester: Optional credit points per semester, such as 24 or 48. Leave empty to use the student's study load.
        start_term: Optional first term such as 2027-S1. Leave empty to start at the student's start term or the first term open for enrolment.
        preferred_option_ids: Optional option course codes or titles the student wants included.

    Returns:
        found and the plan: each semester with its courses, credit points and chosen workshop (with fit), the number of semesters and years, whether it is complete, anything that could not be placed and why, unconfirmed workshops, suggested options, what is already passed or assumed passed, a note comparing with the published duration, and a source block. If nobody is logged in, or an input is invalid, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    try:
        blocks = sch.parse_availability(availability)
    except sch.AvailabilityError as e:
        return not_found(str(e))
    program = prog.program_for(student)
    cap = credit_points_per_semester or prog.credit_per_semester(program, student["study_load"])
    if not isinstance(cap, int) or cap < 12:
        return not_found("credit_points_per_semester must be a whole number of at least 12.")
    if start_term and start_term not in sch.all_terms():
        return not_found(f"There is no timetable for {start_term}. Terms are: {', '.join(sch.all_terms())}.")
    options, chosen = prog.option_pool(program), []
    for query in preferred_option_ids or []:
        matches, _ = find_courses(query, load("courses.json"))
        if len(matches) != 1 or matches[0]["course_id"] not in options:
            return not_found(f"{query!r} is not one option course. Give a course code from the option list.")
        chosen.append(matches[0]["course_id"])
    plan = planning.build_plan(student, blocks, cap, start_term, chosen)
    plan["availability_used"] = [f"{d} {s} to {e}" for d, s, e in blocks] or "none given, so every time counts as free"
    plan["assumptions"] = (["Courses in progress this term are assumed to be passed."] if plan["in_progress_assumed_passed"] else []) + \
                          (["Option courses marked suggested were chosen for you and can be swapped."] if plan["suggested_options"] else [])
    return {"found": True, "plan": plan,
            "source": {**source(program, "programs.json"), "file": "programs.json, courses.json, timetable.json and students.json"}}
