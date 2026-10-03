"""Availability and timetable logic shared by the timetable, plan and enrolment tools."""
import re
from itertools import product

from tools.common import load

DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
AVAILABILITY_FORMAT = 'availability must look like {"busy": [{"days": ["Mon", "Tue"], "start": "09:00", "end": "17:00"}]}'
TIME = re.compile(r"^\d{1,2}:\d{2}$")
LECTURE_NOTE = "Lectures are assumed to be available online with recordings, so only workshops need attending."


class AvailabilityError(ValueError):
    pass


def normalise_day(day) -> str:
    key = str(day).strip().lower()[:3]
    for abbreviation in DAY_ABBREVIATIONS:
        if abbreviation.lower() == key:
            return abbreviation
    raise AvailabilityError(f"{day!r} is not a day of the week. {AVAILABILITY_FORMAT}")


def normalise_time(value) -> str:
    text = str(value).strip()
    if not TIME.match(text) or not (0 <= int(text.split(":")[0]) <= 23 and 0 <= int(text.split(":")[1]) <= 59):
        raise AvailabilityError(f"{value!r} is not a time like 09:00. {AVAILABILITY_FORMAT}")
    return text.zfill(5)


def parse_availability(availability) -> list[tuple[str, str, str]]:
    """The busy blocks as (day, start, end). Nothing given means free at all times."""
    if availability in (None, "", {}):
        return []
    if not isinstance(availability, dict) or not isinstance(availability.get("busy"), list):
        raise AvailabilityError(AVAILABILITY_FORMAT)
    blocks = []
    for block in availability["busy"]:
        if not isinstance(block, dict) or not block.get("days"):
            raise AvailabilityError(f"each busy block needs days, a start and an end. {AVAILABILITY_FORMAT}")
        start, end = normalise_time(block.get("start")), normalise_time(block.get("end"))
        if start >= end:
            raise AvailabilityError(f"a busy block must start before it ends ({start} to {end}).")
        blocks += [(normalise_day(d), start, end) for d in block["days"]]
    return blocks


NO_AVAILABILITY = ("No availability was given, so every workshop was treated as fitting. If the student has told you "
                   "when they are busy, call this tool again with it.")


def availability_used(blocks) -> dict:
    """What a fit check applied, so a result never looks like a real answer when the times were left out."""
    used = {"availability_used": [f"{d} {s} to {e}" for d, s, e in blocks] or "none given, so every time counts as free"}
    return used if blocks else {**used, "warning": NO_AVAILABILITY}


def overlaps(day, start, end, blocks) -> bool:
    return any(d == day and start < e and s < end for d, s, e in blocks)


def fit(option: dict, blocks) -> str:
    """fits, clashes or unknown (the time or mode is missing)."""
    if option["day"] is None or option["start"] is None or option["end"] is None or not option.get("mode"):
        return "unknown"
    return "clashes" if overlaps(option["day"], option["start"], option["end"], blocks) else "fits"


def is_available(option: dict) -> bool:
    return option["enrolment_open"] and option["seats_taken"] < option["seats_total"]


def when_text(option: dict) -> str:
    if option["day"] is None:
        return "time to be confirmed (arranged with the supervisor)"
    return f"{DAY_NAMES[DAY_ABBREVIATIONS.index(option['day'])]} {option['start']} to {option['end']}"


def view(option: dict) -> dict:
    left = option["seats_total"] - option["seats_taken"]
    return {"class_id": option["class_id"], "when": when_text(option), "day": option["day"], "start": option["start"],
            "end": option["end"], "mode": option["mode"], "campus": option["campus"], "seats_left": left,
            "enrolment_open": option["enrolment_open"], "full": left <= 0}


def all_terms() -> list[str]:
    return sorted({o["term"] for o in load("timetable.json")})


def get_offering(course_id: str, term: str):
    return next((o for o in load("timetable.json") if (o["course_id"], o["term"]) == (course_id, term)), None)


def offered_terms(course_id: str) -> list[str]:
    return sorted(o["term"] for o in load("timetable.json") if o["course_id"] == course_id)


def components(offering: dict) -> dict:
    return {c["component"]: c["options"] for c in offering["components"]}


def suggest_lecture(offering: dict):
    """The open lecture option with the most free seats."""
    open_ones = [o for o in components(offering)["lecture"] if is_available(o)]
    return max(open_ones, key=lambda o: o["seats_total"] - o["seats_taken"], default=None)


def offering_fit(offering: dict, blocks) -> dict:
    """Whether a course in a term can be attended, with each workshop labelled fits, clashes or unknown."""
    comp = components(offering)
    workshops = [{**view(o), "fit": fit(o, blocks)} for o in comp["workshop"]]
    lectures = [view(o) for o in comp["lecture"]]
    lecture_ok = any(is_available(o) for o in comp["lecture"])
    usable = [w for w in workshops if not w["full"] and w["enrolment_open"]]
    if not lecture_ok:
        verdict, reason = "no", "no lecture option is open with seats left"
    elif any(w["fit"] == "fits" for w in usable):
        verdict, reason = "yes", "at least one open workshop fits"
    elif any(w["fit"] == "unknown" for w in usable):
        verdict, reason = "unknown", "the workshop time is not confirmed yet"
    elif any(w["fit"] == "fits" for w in workshops):
        verdict, reason = "no", "the workshops that fit are full or closed"
    else:
        verdict, reason = "no", "every workshop clashes"
    return {"term": offering["term"], "can_attend": verdict, "reason": reason, "workshops": workshops,
            "lectures": lectures, "fitting_workshops": sum(w["fit"] == "fits" for w in usable),
            "suggested_lecture": (view(s) if (s := suggest_lecture(offering)) else None)}


def choose_workshops(term: str, course_ids: list[str], blocks, taken=()):
    """One usable workshop per course with none overlapping each other or the times already taken.

    Workshops that fit come before ones with no fixed time. Returns {course_id: option} or None.
    """
    pools = []
    for course_id in course_ids:
        offering = get_offering(course_id, term)
        if offering is None:
            return None
        usable = [o for o in components(offering)["workshop"] if is_available(o) and fit(o, blocks) != "clashes"]
        pools.append(sorted(usable, key=lambda o: fit(o, blocks) != "fits"))
    for combo in product(*pools):
        new = [(o["day"], o["start"], o["end"]) for o in combo if o["day"]]
        pairs = [(a, b) for i, a in enumerate(new) for b in new[i + 1:]] + [(a, b) for a in new for b in taken]
        if not any(a[0] == b[0] and a[1] < b[2] and b[1] < a[2] for a, b in pairs):
            return dict(zip(course_ids, combo))
    return None


def first_open_term() -> str:
    """The first term with any class open for enrolment."""
    return next(t for t in all_terms() if any(
        o["enrolment_open"] for off in load("timetable.json") if off["term"] == t
        for comp in off["components"] for o in comp["options"]))
