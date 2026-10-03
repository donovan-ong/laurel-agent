from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog, scheduling as sch
from tools.common import current_student, find_courses, load, not_found, source

AVAILABILITY_HELP = ('a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]} '
                     "listing the times the student cannot attend, with days as Mon to Sun and times as 24 hour HH:MM")


def one_course(query: str):
    """The single course a query names, or a not-found response the agent can act on."""
    matches, _ = find_courses(query or "", load("courses.json"))
    if not matches:
        return None, not_found(f"There is no course matching {query!r}.")
    if len(matches) > 1:
        return None, {"found": False, "ambiguous": True, "reason": f"{len(matches)} courses match {query!r}. Ask the student which one.",
                      "candidates": [{"course_id": c["course_id"], "title": c["title"]} for c in matches[:12]]}
    return matches[0], None


def offerings_for(course: dict, term):
    terms = sch.offered_terms(course["course_id"])
    if term and term not in terms:
        return None, not_found(f"{course['title']} is not offered in {term}. It runs in: {', '.join(terms)}.")
    return [sch.get_offering(course["course_id"], t) for t in ([term] if term else terms)], None


@tool(permission=ToolPermission.READ_ONLY)
def get_timetable(course_id: str, term: Optional[str] = None) -> dict:
    """Get the class times for a course: its lecture options and workshop options in each term, with day, time, mode, campus, seats left and whether enrolment is open.

    Use this when the student asks when a course runs, what class times or workshop options it has, or whether a class has space. Give a course code, a Handbook code or a title. Leave term empty for every term the course is offered, or pass one such as 2027-S1. A student enrols in one lecture option and one workshop option. Lectures are assumed to be online with recordings, so suggest_lecture and let the student choose.

    Args:
        course_id: The course code, Handbook code or title, for example COSC2148.
        term: Optional term such as 2027-S1.

    Returns:
        found, the course, each offering with lectures, workshops and a suggested lecture, a note about lectures, and a source block. If the course is unknown, ambiguous or not offered in that term, found is false with a reason.
    """
    course, error = one_course(course_id)
    if error:
        return error
    offerings, error = offerings_for(course, term)
    if error:
        return error
    result = []
    for o in offerings:
        comp = sch.components(o)
        suggested = sch.suggest_lecture(o)
        is_open = any(x["enrolment_open"] for c in ("lecture", "workshop") for x in comp[c])
        result.append({"term": o["term"], "enrolment_open": is_open,
                       "enrolment_note": None if is_open else f"Enrolment is closed for {o['term']}, so no class can be enrolled in.",
                       "lectures": [sch.view(x) for x in comp["lecture"]],
                       "workshops": [sch.view(x) for x in comp["workshop"]],
                       "suggested_lecture": sch.view(suggested) if suggested else None})
    return {"found": True, "course": {"course_id": course["course_id"], "title": course["title"],
                                      "credit_points": course["credit_points"]},
            "offerings": result, "lecture_note": sch.LECTURE_NOTE, "source": source(offerings[0], "timetable.json")}


@tool(permission=ToolPermission.READ_ONLY)
def check_availability_fit(course_id: str, availability: Optional[dict] = None, term: Optional[str] = None) -> dict:
    """Check a course's workshops against the times the student cannot attend, labelling each workshop fits, clashes or unknown, and say whether the student can attend the course.

    Use this when the student asks whether a course works for their schedule or which workshop times suit them. If they have already told you when they are busy, use it; otherwise leave availability empty rather than asking first - every workshop will then show as fitting, so say plainly that no time constraints were assumed and invite them to mention one if that's wrong. Lectures are assumed online so they are listed but never labelled. A course can be attended when at least one open workshop with seats fits. A workshop with no fixed time, such as a thesis, is unknown.

    Args:
        course_id: The course code, Handbook code or title.
        availability: The times the student cannot attend, as a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}, with days Mon to Sun and 24 hour HH:MM times. Leave empty if they have no limits.
        term: Optional term such as 2027-S1. Leave empty to check every term the course runs.

    Returns:
        found, and for each term can_attend (yes, no or unknown), the reason, every workshop labelled fits, clashes or unknown with its seats, the lectures, and a source block. If the availability is malformed, found is false with the format to use.
    """
    course, error = one_course(course_id)
    if error:
        return error
    try:
        blocks = sch.parse_availability(availability)
    except sch.AvailabilityError as e:
        return not_found(str(e))
    offerings, error = offerings_for(course, term)
    if error:
        return error
    terms = [sch.offering_fit(o, blocks) for o in offerings]
    return {"found": True, "course": {"course_id": course["course_id"], "title": course["title"]},
            "terms": terms, "can_attend_in": [t["term"] for t in terms if t["can_attend"] == "yes"],
            "unconfirmed_in": [t["term"] for t in terms if t["can_attend"] == "unknown"],
            **sch.availability_used(blocks), "lecture_note": sch.LECTURE_NOTE, "source": source(offerings[0], "timetable.json")}


@tool(permission=ToolPermission.READ_ONLY)
def find_courses_that_fit(context: AgentRun, term: str, availability: Optional[dict] = None, kind: str = "all",
                          include_not_fitting: bool = False) -> dict:
    """List the courses running in a term that the student can attend given the times they cannot, so they can choose or compare courses.

    Use this for questions such as which option courses I can take, what fits around my work, or which courses only run during the day. kind is option (the option list), compulsory or all. Each course says whether it can be attended (yes, no or unknown) and its fitting workshops. Set include_not_fitting to also list the courses that cannot be attended.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        term: The term such as 2027-S1.
        availability: The times the student cannot attend, as a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}. Leave empty for no limits.
        kind: option, compulsory or all. Default all.
        include_not_fitting: If true, also list the courses that cannot be attended.

    Returns:
        found, the courses that can be attended or are unconfirmed with their fitting workshops, counts, the courses that cannot be attended if asked, and a source block. If the term has no timetable, found is false.
    """
    if term not in sch.all_terms():
        return not_found(f"There is no timetable for {term}. Terms are: {', '.join(sch.all_terms())}.")
    if kind not in ("all", "option", "compulsory"):
        return not_found("kind must be option, compulsory or all.")
    try:
        blocks = sch.parse_availability(availability)
    except sch.AvailabilityError as e:
        return not_found(str(e))
    student, error = current_student(context)
    if error:
        return error
    program = prog.program_for(student)
    options = set(prog.option_pool(program))
    in_program = set(prog.compulsory_ids(program)) | options | {c for _, i in prog.items(program) if i["type"] == "choice" for c in i["course_ids"]}
    titles = {c["course_id"]: c for c in load("courses.json")}
    offerings = [o for o in load("timetable.json") if o["term"] == term and o["course_id"] in in_program
                 and (kind == "all" or (o["course_id"] in options) == (kind == "option"))]
    fits, not_fits = [], []
    for o in offerings:
        r = sch.offering_fit(o, blocks)
        entry = {"course_id": o["course_id"], "title": titles[o["course_id"]]["title"],
                 "credit_points": titles[o["course_id"]]["credit_points"],
                 "kind": "option" if o["course_id"] in options else "compulsory",
                 "can_attend": r["can_attend"], "reason": r["reason"]}
        if r["can_attend"] == "no":
            not_fits.append(entry)
        else:
            fitting = [w for w in r["workshops"] if w["fit"] == "fits" and not w["full"] and w["enrolment_open"]]
            fits.append({**entry, "fitting_workshops": [{"class_id": w["class_id"], "when": w["when"], "seats_left": w["seats_left"]} for w in fitting]})
    response = {"found": True, "term": term, "can_attend": [f for f in fits if f["can_attend"] == "yes"],
                "unconfirmed": [f for f in fits if f["can_attend"] == "unknown"],
                "counts": {"offered": len(offerings), "can_attend": sum(f["can_attend"] == "yes" for f in fits),
                           "unconfirmed": sum(f["can_attend"] == "unknown" for f in fits), "cannot_attend": len(not_fits)},
                **sch.availability_used(blocks), "lecture_note": sch.LECTURE_NOTE,
                "source": source(offerings[0], "timetable.json") if offerings else None}
    if include_not_fitting:
        response["cannot_attend"] = not_fits
    return response
