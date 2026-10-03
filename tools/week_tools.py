"""The student's week at a glance. It reads the other tools' results rather than the data files, so the rules
(what counts as overdue, renewable, a hold) stay in one place.
"""
from datetime import date, timedelta
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.calendar_tools import get_current_week, label, resolve_date
from tools.canvas_tools import list_assignments, week_bounds
from tools.common import current_student
from tools.library_tools import get_current_loans
from tools.student_tools import get_fees, get_student_profile

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


def day_text(iso: str) -> str:
    return label(date.fromisoformat(iso))


def in_days(n: int) -> str:
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def open_assignments(context: AgentRun, on: date) -> list[dict]:
    """Unsubmitted assignments that are recently overdue or still to come."""
    result = list_assignments.fn(context=context)
    floor = (on - timedelta(days=RECENT_DAYS)).isoformat()
    return [a for a in result.get("assignments", []) if not a["submitted"] and a["due_date"] >= floor]


def assignment_items(assignments: list[dict], on: date) -> list[dict]:
    _, week_end = week_bounds(on)
    items, later = [], []
    for a in assignments:
        due = date.fromisoformat(a["due_date"])
        name = f"{a['title']} for {a['course_title']}"
        prompt = f"Did I submit {a['title']} for {a['course_title']}?"
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
            items.append({"kind": "assignment", "urgency": "upcoming", "title": f"{a['title']} for {a['course_title']}",
                          "detail": f"Due {day_text(first)} ({in_days((date.fromisoformat(first) - on).days)})",
                          "when": first, "prompt": f"What's due for {a['course_title']}, and when?"})
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
    profile = get_student_profile.fn(context=context)
    sources = [profile["source"]]
    items = []
    hold = profile["student"]["account_hold"]
    if hold:
        items.append({"kind": "hold", "urgency": "action", "title": "Account hold", "detail": hold["message"],
                      "when": None, "prompt": "Do I owe anything, and does it stop me enrolling?"})
    else:
        account = get_fees.fn(context=context)["account"]
        if account["balance_due"]:
            items.append({"kind": "hold", "urgency": "action", "title": f"Balance due: {account['balance_due']} AUD",
                          "detail": f"Due {day_text(account['due_date'])}" if account["due_date"] else "Payment due",
                          "when": account["due_date"], "prompt": "What do I owe and when is it due?"})
    assignments = open_assignments(context, on)
    items += assignment_items(assignments, on)
    loans = get_current_loans.fn(context=context)
    items += loan_items(loans.get("loans", []), on)
    week = get_current_week.fn(on_date=on.isoformat())
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

