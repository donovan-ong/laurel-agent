"""Dropping a class: what it costs and whether it is still allowed. Nothing is stored.

The check id and the reference number are derived from the student, course and term, like enrolment. The rules use the
census date in terms.json and the published last day to drop without academic penalty in key_dates.json.
"""
import hashlib
from datetime import date

from tools import scheduling as sch
from tools.common import load, today as melbourne_today
from tools.calendar_tools import label
from tools.enrolment import NOTICE, SALT, problem


def _digest(student_number: str, course_id: str, term: str) -> str:
    return hashlib.sha256(f"{SALT}|drop|{student_number}|{course_id}|{term}".encode()).hexdigest()


def check_id(student_number: str, course_id: str, term: str) -> str:
    return _digest(student_number, course_id, term)[:16]


def reference(student_number: str, course_id: str, term: str) -> str:
    return f"DROP-{int(_digest(student_number, course_id, term)[:8], 16) % 1_000_000:06d}"


def drop_deadline(term: str) -> date | None:
    """The published last day to drop without academic penalty, or None when RMIT has not published it for this term."""
    for period in load("key_dates.json"):
        if period["period"] == term:
            return next((date.fromisoformat(e["date"]) for e in period["events"] if e["category"] == "drop_deadline"), None)
    return None


def money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.0f}"


def find_enrolment(enrolments, course_id: str, term: str) -> dict | None:
    return next((e for e in enrolments if e["course_id"] == course_id and e["term"] == term), None)


def summarise(enrolment: dict, course: dict) -> dict:
    parts = sch.components(sch.get_offering(enrolment["course_id"], enrolment["term"]))
    pick = lambda component: next(o for o in parts[component] if o["class_id"] in enrolment["class_ids"])
    return {"course_id": course["course_id"], "title": course["title"], "term": enrolment["term"],
            "credit_points": course["credit_points"], "lecture": sch.view(pick("lecture")),
            "workshop": sch.view(pick("workshop"))}


def assess(student: dict, course_id: str, term: str, enrolments=None, today: date | None = None) -> dict:
    """Whether the student can drop this course in this term, with the fee and deadline consequences. Changes nothing.

    enrolments defaults to the student's record. The enrolment service passes the record adjusted for what it has
    enrolled and dropped. today defaults to the date in Melbourne.
    """
    day = today or melbourne_today()
    enrolments = student["current_enrolments"] if enrolments is None else enrolments
    enrolment = find_enrolment(enrolments, course_id, term)
    if enrolment is None:
        return {"can_drop": False, "summary": None, "consequences": None, "reasons": [problem(
            "NOT_ENROLLED", f"You are not enrolled in {course_id} in {term}, so there is nothing to drop.")]}
    course = next(c for c in load("courses.json") if c["course_id"] == course_id)
    calendar = next(t for t in load("terms.json") if t["term"] == term)
    fees = load("fees.json")
    fee_type = fees["fee_types"][student["fee_type"]]
    fee = fee_type["fee_per_12cp"] * course["credit_points"] / 12
    amount = money(fee, fees["currency"])
    census = date.fromisoformat(calendar["census_date"])
    deadline = drop_deadline(term)
    consequences = {"course_fee": fee, "currency": fees["currency"], "fee_type": student["fee_type"],
                    "census_date": calendar["census_date"], "census_when": label(census),
                    "drop_deadline": deadline.isoformat() if deadline else None,
                    "drop_deadline_when": label(deadline) if deadline else None,
                    "withdrawal_rule": fee_type["withdrawal_rule"], "today": day.isoformat()}
    reasons = []
    if date.fromisoformat(calendar["end_date"]) < day:
        phase, message = "term_ended", f"{term} ended on {label(date.fromisoformat(calendar['end_date']))}."
        reasons.append(problem("DROP_DEADLINE_PASSED", f"{term} has already ended, so this class cannot be dropped."))
    elif day < census:
        phase = "before_census"
        message = (f"The census date is {label(census)}. Dropping before it means you are not charged the {amount} fee "
                   f"for this course.")
        consequences["fee_outcome"], consequences["academic_penalty"] = "avoided", False
    elif deadline and day <= deadline:
        phase = "after_census"
        message = (f"The census date ({label(census)}) has passed, so the {amount} fee still applies. You can drop "
                   f"without academic penalty until {label(deadline)}.")
        consequences["fee_outcome"], consequences["academic_penalty"] = "still_payable", False
    elif deadline:
        phase = "after_deadline"
        message = (f"The last day to drop without academic penalty was {label(deadline)}. Speak to Student Connect "
                   f"about your options.")
        reasons.append(problem("DROP_DEADLINE_PASSED", message))
    else:
        phase = "deadline_not_published"
        message = (f"The census date ({label(census)}) has passed, so the {amount} fee still applies. The last day to "
                   f"drop without academic penalty is not in this demo's data, so check it with Student Connect.")
        consequences["fee_outcome"], consequences["academic_penalty"] = "still_payable", None
    consequences["phase"], consequences["message"] = phase, message
    return {"can_drop": not reasons, "reasons": reasons, "summary": summarise(enrolment, course),
            "consequences": consequences}


def check_response(student: dict, course_id: str, term: str, **state) -> dict:
    """What check_drop returns, without the found and source fields."""
    return {**assess(student, course_id, term, **state), "check_id": check_id(student["student_number"], course_id, term),
            "simulation_notice": NOTICE}


def drop_response(student: dict, course_id: str, term: str, cid: str, confirmed, **state) -> dict:
    """What drop_enrolment returns: dropped with a reference, or refused with a coded error. Changes nothing itself."""
    base = {"simulated": True, "notice": NOTICE}

    def refuse(code: str, message: str, **extra) -> dict:
        return {"status": "refused", "error": {"code": code, "message": message}, **extra, **base}

    if confirmed is not True:
        return refuse("NOT_CONFIRMED", "The student has not confirmed. Ask them to confirm and wait for a clear yes.")
    if cid != check_id(student["student_number"], course_id, term):
        return refuse("INVALID_CHECK", "The check_id does not match this course and term. Run check_drop again for them.")
    result = assess(student, course_id, term, **state)
    if not result["can_drop"]:
        first = result["reasons"][0]
        return refuse(first["code"], first["message"], all_reasons=result["reasons"])
    return {"status": "dropped", "reference": reference(student["student_number"], course_id, term),
            "dropped": result["summary"], "consequences": result["consequences"], **base}
