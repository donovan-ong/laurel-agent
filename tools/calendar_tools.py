from datetime import date
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

from tools import common
from tools.common import load, not_found, source

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BREAK_KINDS = ("break", "university_closure")
NEXT_KINDS = ["holiday", "census", "drop_deadline", "withdraw_deadline", "assessment_period", "results_release",
              "classes_begin", "enrolment_opens"]
ORIGIN = "Event names and dates are transcribed from RMIT's published key dates. The categories are our own labels."


def merged_events() -> list[dict]:
    """Every event once, with the periods it appears under (the published lists repeat holidays and closures)."""
    merged = {}
    for period in load("key_dates.json"):
        for e in period["events"]:
            item = merged.setdefault((e["date"], e["end_date"], e["event"]), {
                "date": e["date"], "end_date": e["end_date"], "event": e["event"],
                "category": e["category"], "applies_to": e["applies_to"], "note": e["note"], "periods": []})
            item["periods"].append(period["period"])
    return sorted(merged.values(), key=lambda e: (e["date"], e["end_date"] or e["date"], e["event"]))


def label(day: date) -> str:
    return f"{DAY_NAMES[day.weekday()]} {day.day} {day.strftime('%B %Y')}"


def when(start: date, end: date) -> str:
    """The dates as text to quote as they are, for example Monday 26 October 2026 to Friday 13 November 2026."""
    return label(start) if start == end else f"{label(start)} to {label(end)}"


def annotate(event: dict, on: date) -> dict:
    """Add whether the event is past, happening now or upcoming, how many days away it is, and the dates as text."""
    start = date.fromisoformat(event["date"])
    end = date.fromisoformat(event["end_date"] or event["date"])
    status = "past" if end < on else "happening_now" if start <= on else "upcoming"
    return {**event, "when": when(start, end), "status": status,
            "days_until_start": (start - on).days, "days_until_end": (end - on).days}


def resolve_date(on_date: Optional[str]):
    if not on_date:
        return common.today(), "clock (Melbourne)", None
    try:
        return date.fromisoformat(on_date), "provided", None
    except ValueError:
        return None, None, not_found(f"on_date must look like 2026-09-21, not {on_date!r}.")


def week_for(period: dict, on: date):
    """The week containing a date. The mid-semester break wins over the numbered week it overlaps."""
    spans = [(w, date.fromisoformat(w["start"]), date.fromisoformat(w["end"])) for w in period["weeks"]]
    inside = [w for w, a, b in spans if a <= on <= b]
    return next((w for w in inside if w["label"] == "Mid-semester break"), inside[0] if inside else None)


@tool(permission=ToolPermission.READ_ONLY)
def get_current_week(on_date: Optional[str] = None) -> dict:
    """Get what week of the semester it is today (or on a given date), what is happening on that day, and the next key dates.

    Use this for "what week is it", "are we in the break", "what is happening this week", "what is coming up" or "when is the next break, exam period, results release or census". Leave on_date empty for today, or pass a date like 2026-09-21. It reports the numbered teaching week or mid-semester break for Semester 1 and Semester 2. If teaching_weeks is empty the date is not in a teaching week, for example in the semester break or over the holidays, so use happening_now. next_break and previous_break answer "when is the uni break": a mid-semester break, semester break or the closure over the holidays, never a public holiday. next_break is null when none is left. next_by_category gives the next event of each other main kind (holiday, census, drop_deadline, withdraw_deadline, assessment_period, results_release, classes_begin, enrolment_opens), and a kind is missing when nothing of that kind is left. State the date you used.

    Args:
        on_date: Optional date as YYYY-MM-DD. Leave empty for today in Melbourne.

    Returns:
        found, the date and weekday, teaching_weeks, happening_now events, the next few upcoming events, next_break, previous_break, next_by_category, each with days until it starts, and a source block. If the date is outside the published calendar (1 September 2025 to 26 February 2027), found is false.
    """
    on, origin, error = resolve_date(on_date)
    if error:
        return error
    periods = load("key_dates.json")
    events = merged_events()
    first = min(e["date"] for e in events)
    last = max(e["end_date"] or e["date"] for e in events)
    if not first <= on.isoformat() <= last:
        return not_found(f"The published calendar covers {first} to {last}, and {on.isoformat()} is outside it.")
    annotated = [annotate(e, on) for e in events]
    upcoming = [e for e in annotated if e["status"] == "upcoming"]
    next_by_category = {}
    for e in upcoming:
        if e["category"] in NEXT_KINDS:
            next_by_category.setdefault(e["category"], e)
    breaks = [e for e in annotated if e["category"] in BREAK_KINDS]
    past_breaks = [e for e in breaks if e["status"] == "past"]
    weeks = []
    for period in periods:
        week = week_for(period, on)
        if week:
            weeks.append({"period": period["period"], "name": period["name"], "week": week["label"],
                          "week_start": week["start"], "week_end": week["end"],
                          "when": when(date.fromisoformat(week["start"]), date.fromisoformat(week["end"]))})
    return {
        "found": True,
        "date": on.isoformat(),
        "date_text": label(on),
        "weekday": DAY_NAMES[on.weekday()],
        "date_from": origin,
        "in_teaching_week": any(w["week"] != "Mid-semester break" for w in weeks),
        "teaching_weeks": weeks,
        "happening_now": [e for e in annotated if e["status"] == "happening_now"],
        "next_events": upcoming[:6],
        "next_break": next((e for e in breaks if e["status"] != "past"), None),
        "previous_break": max(past_breaks, key=lambda e: e["days_until_end"], default=None),
        "next_by_category": {k: next_by_category[k] for k in NEXT_KINDS if k in next_by_category},
        "origin": ORIGIN,
        "source": source(periods[0], "key_dates.json"),
    }


@tool(permission=ToolPermission.READ_ONLY)
def get_key_dates(period: Optional[str] = None, category: Optional[str] = None, on_date: Optional[str] = None,
                  upcoming_only: bool = False, include_weeks: bool = False, limit: int = 20) -> dict:
    """Look up RMIT key dates: the uni break, the exam (assessment) period, results release, census date, add, drop and withdraw deadlines, holidays, closures, orientation, enrolment opening and graduation.

    Use this for questions like "when is the break", "when are exams", "when are results released", "what is the census date", "when are the public holidays" or "when does semester 2 start". Filter by period and category, and set upcoming_only to skip dates already past. Every event says whether it is past, happening now or upcoming and how many days away it is, counted from today unless on_date is given. Each has a when text such as "Monday 26 October 2026 to Friday 13 November 2026": quote it as it is and do not reformat or recompute dates.

    Periods: 2026-S1 (Semester 1 2026), 2026-S2 (Semester 2 2026), 2025-SPR (Spring Semester 2025-2026), 2026-SUM (Summer Semester 2026), 2026-SPR (Spring Semester 2026-2027).
    Categories: add_deadline, assessment_period (the exam period), break, census, classes_begin, classes_end, classes_resume, deferred_assessment_period, drop_deadline, enrolment_opens, equitable_assessment_deadline, graduation, holiday, orientation, re_enrolment_deadline, results_release, university_closure, university_reopens, withdraw_deadline.
    Add deadlines differ by school: applies_to says which. Students in computing programs are in all_other_schools.

    Args:
        period: Optional period id such as 2026-S2.
        category: Optional category such as assessment_period.
        on_date: Optional date as YYYY-MM-DD to count days from. Leave empty for today in Melbourne.
        upcoming_only: If true, leave out events that have already finished.
        include_weeks: If true, also return the week table (week 1 to 16 and the mid-semester break) for Semester 1 and 2.
        limit: The most events to return. Default 20.

    Returns:
        found, the matching events in date order, whether more are available, the week table if asked, and a source block. If nothing matches or the period or category is unknown, found is false with a reason.
    """
    on, origin, error = resolve_date(on_date)
    if error:
        return error
    periods = load("key_dates.json")
    events = merged_events()
    ids = [p["period"] for p in periods]
    categories = sorted({e["category"] for e in events})
    if period and period not in ids:
        return not_found(f"Unknown period {period!r}. Periods are: {', '.join(ids)}.")
    if category and category not in categories:
        return not_found(f"Unknown category {category!r}. Categories are: {', '.join(categories)}.")
    matches = [annotate(e, on) for e in events
               if (not period or period in e["periods"]) and (not category or e["category"] == category)]
    if upcoming_only:
        matches = [e for e in matches if e["status"] != "past"]
    if not matches:
        return not_found("No key dates match those filters.")
    response = {
        "found": True,
        "date": on.isoformat(),
        "date_from": origin,
        "events": matches[:max(limit, 1)],
        "more_available": len(matches) > max(limit, 1),
        "origin": ORIGIN,
        "source": source(periods[0], "key_dates.json"),
    }
    if include_weeks:
        response["weeks"] = {p["period"]: p["weeks"] for p in periods if p["weeks"] and (not period or p["period"] == period)}
    return response
