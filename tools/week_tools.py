"""The student's week at a glance, and study sessions planned around it. Both read the other tools' results
rather than the data files, so the rules (what counts as overdue, renewable, a hold) stay in one place. The
other tools are reached through their modules, never imported by name: `orchestrate tools import` registers
every tool it finds in this file's namespace, which would re-register them from here.
"""
from datetime import date, timedelta
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import calendar_tools, canvas_tools, library_tools, scheduling as sch, student_tools, study_week
from tools.calendar_tools import label, resolve_date
from tools.canvas_tools import week_bounds
from tools.common import current_student, load, not_found, source, today

URGENCY = ["action", "overdue", "today", "soon", "upcoming", "suggestion"]
KINDS = ["hold", "assignment", "loan", "key_date", "plan"]
RECENT_DAYS = 21
KEY_DATE_DAYS = 28
KEY_DATE_PROMPTS = {
    "census": "When is the census date, and what happens if I drop a class before it?",
    "drop_deadline": "What is the last day to drop a class without penalty?",
    "withdraw_deadline": "What is the last day to withdraw from a class?",
    "assessment_period": "When do exams start and when are results released?",
    "results_release": "When are results released?",
}
STUDY_NOTE = ("These are suggested study sessions only: nothing has been booked. Any room can be booked through "
              "check_room_availability and book_room once the student confirms.")


def day_text(iso: str) -> str:
    return label(date.fromisoformat(iso))


def in_days(n: int) -> str:
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def open_assignments(context: AgentRun, on: date) -> list[dict]:
    """Unsubmitted assignments that are recently overdue or still to come."""
    result = canvas_tools.list_assignments.fn(context=context)
    floor = (on - timedelta(days=RECENT_DAYS)).isoformat()
    return [a for a in result.get("assignments", []) if not a["submitted"] and a["due_date"] >= floor]


def assignment_items(assignments: list[dict], on: date) -> list[dict]:
    _, week_end = week_bounds(on)
    items, later = [], []
    for a in assignments:
        due = date.fromisoformat(a["due_date"])
        name = f"{a['full_title']} ({a['course_title']})"
        prompt = f"Did I submit {a['full_title']} for {a['course_title']}?"
        if due < on:
            items.append({"kind": "assignment", "urgency": "overdue", "title": name,
                          "detail": f"Was due {day_text(a['due_date'])} and has not been submitted",
                          "when": a["due_date"], "prompt": prompt})
        elif due <= week_end:
            items.append({"kind": "assignment", "urgency": "today" if due == on else "soon", "title": name,
                          "detail": f"Due {day_text(a['due_date'])}, not submitted yet",
                          "when": a["due_date"], "prompt": prompt})
        else:
            later.append(a)
    if later:
        first = min(a["due_date"] for a in later)
        for a in (a for a in later if a["due_date"] == first):
            items.append({"kind": "assignment", "urgency": "upcoming", "title": f"{a['full_title']} ({a['course_title']})",
                          "detail": f"Due {day_text(first)} ({in_days((date.fromisoformat(first) - on).days)})",
                          "when": first, "prompt": f"What is {a['full_title']} for {a['course_title']} about?"})
    return items


def loan_items(loans: list[dict], on: date) -> list[dict]:
    items = []
    for loan in loans:
        due = date.fromisoformat(loan["due_date"])
        if due > on + timedelta(days=7):
            continue
        renew = "it can be renewed" if loan["renewable"] else f"it cannot be renewed: {loan['reason']['message']}"
        overdue = due < on
        items.append({"kind": "loan", "urgency": "overdue" if overdue else "soon",
                      "title": f"Library book {'overdue' if overdue else 'due soon'}: {loan['title']}",
                      "detail": f"{'Was due' if overdue else 'Due'} {day_text(loan['due_date'])}; {renew}",
                      "when": loan["due_date"], "prompt": "Can I renew everything?"})
    return items


def key_date_items(week: dict) -> list[dict]:
    items = []
    for category, prompt in KEY_DATE_PROMPTS.items():
        e = week["next_by_category"].get(category)
        if e and e["days_until_start"] <= KEY_DATE_DAYS:
            items.append({"kind": "key_date", "urgency": "soon" if e["days_until_start"] <= 7 else "upcoming",
                          "title": e["event"], "detail": f"{e['when']} ({in_days(e['days_until_start'])})",
                          "when": e["date"], "prompt": prompt})
    e = week.get("next_break")
    if e and e["days_until_start"] <= KEY_DATE_DAYS:
        items.append({"kind": "key_date", "urgency": "upcoming", "title": e["event"],
                      "detail": f"{e['when']} ({in_days(e['days_until_start'])})", "when": e["date"],
                      "prompt": "When is the next uni break?"})
    return items


def week_label(week: dict) -> Optional[str]:
    if not week.get("found"):
        return None
    if week["teaching_weeks"]:
        w = week["teaching_weeks"][0]
        return f"{w['week']}, {w['name']}"
    now = week["happening_now"]
    return now[0]["event"] if now else "Not a teaching week"


@tool(permission=ToolPermission.READ_ONLY)
def get_my_week(context: AgentRun, on_date: Optional[str] = None) -> dict:
    """Get the logged-in student's week at a glance: anything overdue or due soon, holds, library books, and upcoming key dates, most urgent first.

    Use this for "what's my week looking like", "is there anything I should know", "what should I focus on" or "what's coming up for me". It combines the student's account, Canvas assignments, library loans and the published key dates, so one call is enough. Each item has an urgency (action, overdue, today, soon, upcoming or suggestion) and a prompt: a follow-up question the student could ask about it.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        on_date: Optional date as YYYY-MM-DD to treat as today. Leave empty for today in Melbourne.

    Returns:
        found, the date, week_label (the teaching week, if any), items in urgency order, and the sources used. If nobody is logged in, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    on, _, error = resolve_date(on_date)
    if error:
        return error
    profile = student_tools.get_student_profile.fn(context=context)
    sources = [profile["source"]]
    items = []
    hold = profile["student"]["account_hold"]
    if hold:
        items.append({"kind": "hold", "urgency": "action", "title": "Account hold", "detail": hold["message"],
                      "when": None, "prompt": "Do I owe anything, and does it stop me enrolling?"})
    else:
        account = student_tools.get_fees.fn(context=context)["account"]
        if account["balance_due"]:
            items.append({"kind": "hold", "urgency": "action", "title": f"Balance due: {account['balance_due']} AUD",
                          "detail": f"Due {day_text(account['due_date'])}" if account["due_date"] else "Payment due",
                          "when": account["due_date"], "prompt": "What do I owe and when is it due?"})
    assignments = open_assignments(context, on)
    items += assignment_items(assignments, on)
    loans = library_tools.get_current_loans.fn(context=context)
    items += loan_items(loans.get("loans", []), on)
    week = calendar_tools.get_current_week.fn(on_date=on.isoformat())
    if week.get("found"):
        items += key_date_items(week)
        sources.append(week["source"])
    if assignments:
        items.append({"kind": "plan", "urgency": "suggestion", "title": "Plan my study week",
                      "detail": "Study sessions around your classes, each with a free study room",
                      "when": None, "prompt": "Plan my study week"})
    items.sort(key=lambda i: (URGENCY.index(i["urgency"]), KINDS.index(i["kind"]), i["when"] or "9999"))
    if loans.get("source"):
        sources.append(loans["source"])
    return {"found": True, "date": on.isoformat(), "date_text": label(on), "name": student["name"],
            "week_label": week_label(week), "items": items, "sources": sources}


@tool(permission=ToolPermission.READ_ONLY)
def plan_study_week(context: AgentRun, availability: Optional[dict] = None, on_date: Optional[str] = None,
                    max_sessions: int = 6) -> dict:
    """Suggest study sessions for the next seven days for the logged-in student's unsubmitted assignments, placed around their workshops and any times they are busy, each with a free study room.

    Use this for "plan my study week", "when should I study", "help me catch up" or "how do I fit in my assignments". Overdue work comes first, then whatever is due soonest. Sessions are two hours, at most two a day, and never clash with the student's own workshops (lectures are online with recordings). If the student has said when they are busy, for example at work, pass it as availability; otherwise leave it empty and say no other commitments were assumed. Nothing is booked: offer to book a session's room through check_room_availability and book_room, with the student's confirmation.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        availability: The times the student cannot study, as a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}, with days Mon to Sun and 24 hour HH:MM times. Leave empty if none are known.
        on_date: Optional date as YYYY-MM-DD for the first day of the plan. Leave empty for today in Melbourne.
        max_sessions: The most sessions to suggest for the week, 6 unless the student asks for more or fewer.

    Returns:
        found, the week planned, sessions in date order (date, time, course, assignment, due date, whether it is overdue, and a suggested free room), unscheduled assignments with the reason, busy_used, a note that nothing is booked, and the sources. If nobody is logged in or the availability is malformed, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    on, _, error = resolve_date(on_date)
    if error:
        return error
    try:
        stated = sch.parse_availability(availability)
    except sch.AvailabilityError as e:
        return not_found(str(e))
    week = calendar_tools.get_current_week.fn(on_date=on.isoformat())
    term = week["teaching_weeks"][0]["period"] if week.get("found") and week["teaching_weeks"] else None
    classes = study_week.class_blocks(student["current_enrolments"], term)
    busy = stated + [(c["day"], c["start"], c["end"]) for c in classes]
    after = study_week.now_melbourne().strftime("%H:%M") if not on_date and on == today() else None
    spaces = load("study_spaces.json")
    assignments = open_assignments(context, on)
    result = study_week.plan(assignments, busy, spaces["rooms"], spaces["bookings"], on, after, max(1, max_sessions))
    end = on + timedelta(days=study_week.DAYS - 1)
    return {
        "found": True,
        "week": {"start": on.isoformat(), "end": end.isoformat(), "when": f"{label(on)} to {label(end)}"},
        **result,
        "busy_used": [f"{c['what']}: {c['day']} {c['start']} to {c['end']}" for c in classes]
                     + [f"you said busy: {d} {s} to {e}" for d, s, e in stated],
        "availability_used": [f"{d} {s} to {e}" for d, s, e in stated] or "none given, so only workshops were avoided",
        "note": STUDY_NOTE,
        "sources": [source(spaces, "study_spaces.json")] + ([week["source"]] if week.get("found") else []),
    }
