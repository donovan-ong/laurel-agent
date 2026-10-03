"""Study sessions for the coming week, placed around the student's classes and stated commitments, each with a
free study room. A suggestion only: nothing is booked or stored, and booking a room still goes through
check_room_availability and book_room with the student's confirmation.
"""
from datetime import date, datetime, timedelta, timezone

from tools import scheduling as sch
from tools.enrolment import find_class
from tools.studyspaces import available_rooms, view

DAYS = 7
SLOTS = [("09:00", "11:00"), ("11:00", "13:00"), ("14:00", "16:00"), ("16:00", "18:00"), ("19:00", "21:00")]
MAX_PER_DAY = 2


def now_melbourne() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Melbourne"))
    except (ImportError, KeyError, OSError):
        return datetime.now(timezone(timedelta(hours=10)))


def class_blocks(enrolments: list[dict], term: str | None) -> list[dict]:
    """The workshop times of the student's classes in a term, as busy blocks. Lectures are online with
    recordings (scheduling.LECTURE_NOTE), so they are left free like everywhere else."""
    blocks = []
    for e in enrolments:
        if e["term"] != term:
            continue
        for class_id in e["class_ids"]:
            found = find_class(class_id)
            if found and found[1] == "workshop" and found[2].get("day") and found[2].get("start"):
                option = found[2]
                blocks.append({"day": option["day"], "start": option["start"], "end": option["end"],
                               "what": f"{e['course_id']} workshop"})
    return blocks


def sessions_wanted(assignment: dict, on: date) -> int:
    due = date.fromisoformat(assignment["due_date"])
    return 2 if due <= on + timedelta(days=DAYS) else 1


def plan(assignments: list[dict], busy: list[tuple[str, str, str]], rooms: list[dict], bookings: list[dict],
         on: date, after: str | None = None, max_sessions: int = 6) -> dict:
    """Place sessions in the earliest free slots, most urgent assignment first.

    `after` skips today's slots that start before that time. An assignment due within the window only gets
    slots up to its due date. Each session takes the first room free for that slot.
    """
    todo = sorted((a for a in assignments if not a["submitted"]), key=lambda a: a["due_date"])
    slots = []
    for offset in range(DAYS):
        day = on + timedelta(days=offset)
        weekday = sch.DAY_ABBREVIATIONS[day.weekday()]
        for start, end in SLOTS:
            if offset == 0 and after and start < after:
                continue
            if not sch.overlaps(weekday, start, end, busy):
                slots.append((day, weekday, start, end))
    sessions, unscheduled, used, per_day = [], [], set(), {}
    for a in todo:
        due = date.fromisoformat(a["due_date"])
        placed = 0
        for slot in slots:
            day, weekday, start, end = slot
            if len(sessions) >= max_sessions or placed >= sessions_wanted(a, on):
                break
            if slot in used or per_day.get(day, 0) >= MAX_PER_DAY or (due >= on and day > due):
                continue
            free = available_rooms(rooms, bookings, day.isoformat(), start, end)
            used.add(slot)
            per_day[day] = per_day.get(day, 0) + 1
            placed += 1
            sessions.append({"date": day.isoformat(), "weekday": weekday, "start": start, "end": end,
                             "course_id": a["course_id"], "course_title": a["course_title"],
                             "assignment": a["full_title"], "due_date": a["due_date"],
                             "overdue": due < on, "room": view(free[0]) if free else None})
        if placed == 0:
            reason = ("the session limit for the week was reached" if len(sessions) >= max_sessions
                      else "no free slot this week before it is due")
            unscheduled.append({"course_id": a["course_id"], "assignment": a["full_title"], "due_date": a["due_date"],
                                "reason": reason})
    sessions.sort(key=lambda s: (s["date"], s["start"]))
    return {"sessions": sessions, "unscheduled": unscheduled}
