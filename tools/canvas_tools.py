from datetime import date, timedelta
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.calendar_tools import label, resolve_date
from tools.common import current_student, load, not_found, source


def due_status(due: date, submitted: bool, on: date) -> str:
    """Where an assignment stands on a date, as text to quote: the model never works this out itself."""
    days = (due - on).days
    if submitted:
        return "submitted"
    if days < 0:
        return f"overdue by {-days} day{'s' if days != -1 else ''}"
    return "due today" if days == 0 else "due tomorrow" if days == 1 else f"due in {days} days"


def week_bounds(on: date) -> tuple[date, date]:
    """The Monday to Sunday span containing a date."""
    start = on - timedelta(days=on.weekday())
    return start, start + timedelta(days=6)


@tool(permission=ToolPermission.READ_ONLY)
def list_assignments(context: AgentRun, course_id: Optional[str] = None,
                     due_this_week_only: bool = False, on_date: Optional[str] = None) -> dict:
    """Get the logged-in student's Canvas assignments: due date, whether it was submitted and when, and the mark and feedback once graded.

    Use this for "what's due this week", "did I submit assignment 2", "what mark did I get for my first
    assignment" or "what is the data pre-processing assignment about", or any question about coursework due
    dates, submission status, what an assignment involves or a specific assignment's grade. title says which
    one it is (Assignment 1, Assignment 2, and so on), so match "my first assignment" to Assignment 1; name is
    its topic, so match "the data pre-processing assignment" by name. Refer to an assignment by full_title,
    for example "Assignment 1: Data Pre-processing", and say which course (course_title) it belongs to.
    summary is a one-sentence description of the assignment: give it when the student asks about that
    specific assignment. An assignment not yet submitted has submitted false and submitted_at and mark both
    null: never guess a mark for one. due_status ("overdue by 5 days", "due in 3 days", "submitted") and
    days_until_due are worked out from date_used, which is today: quote them, and never work out how far away
    a due date is yourself. The snapshot date in the source block is when the data was made, not today.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        course_id: Optional course code, for example COSC2148, to see only that course's assignments.
        due_this_week_only: If true, only assignments due Monday to Sunday of the current week.
        on_date: Optional date as YYYY-MM-DD to treat as today, for the current week and for due_status. Leave empty for today in Melbourne.

    Returns:
        found, the matching assignments in due-date order, each with its title, name, full_title, one-sentence summary, due_text, due_status and days_until_due, date_used (today), the week used if due_this_week_only was set, and a source block. A student with no current or completed courses has an empty list, not an error. If nobody is logged in, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    courses = {c["course_id"]: c for c in load("courses.json")}
    if course_id and course_id not in courses:
        return not_found(f"Unknown course {course_id}.")
    raw = load("canvas.json")
    items = [a for a in raw if a["student_number"] == student["student_number"]]
    if course_id:
        items = [a for a in items if a["course_id"] == course_id]
    on, _, date_error = resolve_date(on_date)
    if date_error:
        return date_error
    week_start = week_end = None
    if due_this_week_only:
        week_start, week_end = week_bounds(on)
        items = [a for a in items if week_start.isoformat() <= a["due_date"] <= week_end.isoformat()]
    items = sorted(items, key=lambda a: (a["due_date"], a["sequence"]))
    listed = [{
        "course_id": a["course_id"], "course_title": courses[a["course_id"]]["title"], "term": a["term"],
        "assignment_id": a["assignment_id"], "title": a["title"], "name": a["name"],
        "full_title": f"{a['title']}: {a['name']}", "summary": a["summary"], "sequence": a["sequence"],
        "due_date": a["due_date"], "due_text": label(date.fromisoformat(a["due_date"])),
        "due_status": due_status(date.fromisoformat(a["due_date"]), a["submitted"], on),
        "days_until_due": (date.fromisoformat(a["due_date"]) - on).days,
        "max_mark": a["max_mark"], "submitted": a["submitted"],
        "submitted_at": a["submitted_at"], "mark": a["mark"], "feedback": a["feedback"],
    } for a in items]
    response = {"found": True, "date_used": on.isoformat(), "date_used_text": label(on), "assignments": listed,
                "source": source(raw[0], "canvas.json")}
    if due_this_week_only:
        response["week"] = {"start": week_start.isoformat(), "end": week_end.isoformat()}
    return response
