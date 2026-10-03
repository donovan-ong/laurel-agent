"""Enrolment checks shared by check_enrolment and submit_enrolment.

Nothing is stored. The check id and the reference number are derived from the student and the classes, so
submit_enrolment can verify a check without any saved state.
"""
import hashlib

from tools import scheduling as sch
from tools.common import load

SALT = "study-planner-demo"
NOTICE = "SIMULATION: this is a demonstration. No real enrolment has been made, and all the data is synthetic."
PASS_MARK = 50
# When several things are wrong, submit_enrolment reports the first of these
PRIORITY = ["INVALID_SELECTION", "ENROLMENT_CLOSED", "ACCOUNT_HOLD", "PREREQUISITE_NOT_MET",
            "ALREADY_ENROLLED", "ALREADY_PASSED", "CLASS_FULL", "TIMETABLE_CLASH"]


def _digest(student_number: str, class_ids) -> str:
    return hashlib.sha256(f"{SALT}|{student_number}|{','.join(sorted(map(str, class_ids)))}".encode()).hexdigest()


def check_id(student_number: str, class_ids) -> str:
    return _digest(student_number, class_ids)[:16]


def reference(student_number: str, class_ids) -> str:
    return f"SIM-{int(_digest(student_number, class_ids)[:8], 16) % 1_000_000:06d}"


def find_class(class_id: str):
    """(offering, component, option) for a class number, or None."""
    for offering in load("timetable.json"):
        for comp in offering["components"]:
            for option in comp["options"]:
                if option["class_id"] == class_id:
                    return offering, comp["component"], option
    return None


def problem(code: str, message: str, **extra) -> dict:
    return {"code": code, "message": message, **extra}


def adjusted(option: dict, taken: dict | None) -> dict:
    """The option with its seats taken changed by what the enrolment service has added or freed."""
    change = (taken or {}).get(option["class_id"], 0)
    return {**option, "seats_taken": max(0, option["seats_taken"] + change)} if change else option


def effective_enrolments(student: dict, extra=None, dropped=None) -> list[dict]:
    """The student's enrolments on record without the dropped ones, then any made through the service."""
    gone = {tuple(d) for d in (dropped or [])}
    kept = [e for e in student["current_enrolments"] if (e["course_id"], e["term"]) not in gone]
    return kept + list(extra or [])


def alternatives(offering: dict, component: str, exclude: str, taken: dict | None = None) -> list[dict]:
    options = [adjusted(o, taken) for o in sch.components(offering)[component] if o["class_id"] != exclude]
    return [sch.view(o) for o in options if sch.is_available(o)][:5]


def evaluate(student: dict, class_ids, blocks, extra_enrolments=None, dropped=None, taken=None) -> dict:
    """Whether the student can enrol in these classes, and every reason if not. Changes nothing.

    With no extra_enrolments, dropped or taken this uses the student's record alone. The enrolment service passes
    what it has added or dropped (course and term pairs) and the seats it has taken or freed by class number.
    """
    ids = [str(c) for c in (class_ids or [])]
    if len(ids) != 2 or len(set(ids)) != 2:
        return {"eligible": False, "summary": None, "notes": [], "reasons": [problem(
            "INVALID_SELECTION", "Give exactly two different class numbers: one lecture and one workshop.")]}
    found = {cid: find_class(cid) for cid in ids}
    missing = [cid for cid, f in found.items() if f is None]
    if missing:
        return {"eligible": False, "summary": None, "notes": [], "reasons": [problem(
            "INVALID_SELECTION", f"There is no class {', '.join(missing)}.")]}
    offerings = {(f[0]["course_id"], f[0]["term"]) for f in found.values()}
    components = sorted(f[1] for f in found.values())
    if len(offerings) != 1:
        reason = "The classes must belong to the same course and term."
    elif components != ["lecture", "workshop"]:
        reason = f"Choose exactly one lecture and one workshop, not {' and '.join(components)}."
    else:
        reason = None
    if reason:
        return {"eligible": False, "summary": None, "notes": [], "reasons": [problem("INVALID_SELECTION", reason)]}

    offering = next(iter(found.values()))[0]
    chosen = {f[1]: adjusted(f[2], taken) for f in found.values()}
    enrolments = effective_enrolments(student, extra_enrolments, dropped)
    courses = {c["course_id"]: c for c in load("courses.json")}
    course = courses[offering["course_id"]]
    passed = {r["course_id"] for r in student["results"] if r["mark"] >= PASS_MARK}
    reasons, notes = [], []
    for component, option in chosen.items():
        if not option["enrolment_open"]:
            reasons.append(problem("ENROLMENT_CLOSED", f"Enrolment is closed for {component} class {option['class_id']}.",
                                   alternatives=alternatives(offering, component, option["class_id"], taken)))
        if option["seats_taken"] >= option["seats_total"]:
            reasons.append(problem("CLASS_FULL", f"{component.capitalize()} class {option['class_id']} is full "
                                   f"({option['seats_taken']} of {option['seats_total']} seats taken).",
                                   alternatives=alternatives(offering, component, option["class_id"], taken)))
    hold = student["account"]["hold"]
    if hold and "enrolment" in hold["blocks"]:
        reasons.append(problem("ACCOUNT_HOLD", hold["message"]))
    missing_prereqs = [p for p in course["prerequisites"] if p not in passed]
    if missing_prereqs:
        names = ", ".join(f"{courses[p]['title']} ({p})" for p in missing_prereqs)
        reasons.append(problem("PREREQUISITE_NOT_MET", f"{course['title']} needs {names} passed first."))
    if any(e["course_id"] == course["course_id"] and e["term"] == offering["term"] for e in enrolments):
        reasons.append(problem("ALREADY_ENROLLED", f"You are already enrolled in {course['title']} in {offering['term']}."))
    if course["course_id"] in passed:
        reasons.append(problem("ALREADY_PASSED", f"You have already passed {course['title']}."))
    workshop = chosen["workshop"]
    if sch.fit(workshop, blocks) == "clashes":
        reasons.append(problem("TIMETABLE_CLASH", f"The workshop ({sch.when_text(workshop)}) clashes with the times you cannot attend."))
    elif sch.fit(workshop, blocks) == "unknown":
        notes.append("The workshop time is not confirmed yet, so it cannot be checked against your availability.")
    for e in enrolments:
        if e["term"] != offering["term"] or e["course_id"] == course["course_id"] or not workshop["day"]:
            continue
        other = next((o for o in sch.components(sch.get_offering(e["course_id"], e["term"]))["workshop"]
                      if o["class_id"] in e["class_ids"]), None)
        if other and other["day"] and sch.overlaps(workshop["day"], workshop["start"], workshop["end"],
                                                   [(other["day"], other["start"], other["end"])]):
            reasons.append(problem("TIMETABLE_CLASH", f"The workshop ({sch.when_text(workshop)}) overlaps your "
                                   f"{courses[e['course_id']]['title']} workshop ({sch.when_text(other)})."))
    reasons.sort(key=lambda r: PRIORITY.index(r["code"]))
    summary = {"course_id": course["course_id"], "title": course["title"], "term": offering["term"],
               "lecture": sch.view(chosen["lecture"]), "workshop": sch.view(workshop)}
    return {"eligible": not reasons, "reasons": reasons, "summary": summary, "notes": notes}


def check_response(student: dict, class_ids, blocks, **state) -> dict:
    """What check_enrolment returns, without the found and source fields. state is passed to evaluate."""
    result = evaluate(student, class_ids, blocks, **state)
    return {**result, "check_id": check_id(student["student_number"], class_ids or []), "simulation_notice": NOTICE}


def submit_response(student: dict, class_ids, cid: str, confirmed, blocks, **state) -> dict:
    """What submit_enrolment returns: enrolled with a reference, or refused with a coded error. Changes nothing itself."""
    base = {"simulated": True, "notice": NOTICE}

    def refuse(code: str, message: str, **extra) -> dict:
        return {"status": "refused", "error": {"code": code, "message": message}, **extra, **base}

    if confirmed is not True:
        return refuse("NOT_CONFIRMED", "The student has not confirmed. Ask them to confirm and wait for a clear yes.")
    if cid != check_id(student["student_number"], class_ids or []):
        return refuse("INVALID_CHECK", "The check_id does not match these classes. Run check_enrolment again for them.")
    result = evaluate(student, class_ids, blocks, **state)
    if not result["eligible"]:
        first = result["reasons"][0]
        return refuse(first["code"], first["message"], all_reasons=result["reasons"])
    return {"status": "enrolled", "reference": reference(student["student_number"], class_ids),
            "enrolment": result["summary"], "notes": result["notes"], **base}


def describe(enrolments) -> list[dict]:
    """Enrolments with course titles and the lecture and workshop times of each, for list_enrolments and the service."""
    courses = {c["course_id"]: c for c in load("courses.json")}
    current = sch.first_open_term()
    described = []
    for e in enrolments:
        parts = sch.components(sch.get_offering(e["course_id"], e["term"]))
        pick = lambda component: next(o for o in parts[component] if o["class_id"] in e["class_ids"])
        described.append({"course_id": e["course_id"], "title": courses[e["course_id"]]["title"], "term": e["term"],
                          "status": "enrolled, this term" if e["term"] < current else "enrolled, future term",
                          "lecture": sch.view(pick("lecture")), "workshop": sch.view(pick("workshop"))})
    return described
