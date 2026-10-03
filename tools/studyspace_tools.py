from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import studyspaces as rooms
from tools.common import current_student, load, source


@tool(permission=ToolPermission.READ_ONLY)
def check_room_availability(context: AgentRun, date: str, start: str, end: Optional[str] = None,
                            building: Optional[str] = None, party_size: Optional[int] = None,
                            room_id: Optional[str] = None) -> dict:
    """Find a free study room, or check whether one specific room can be booked. This changes nothing.

    Leave room_id empty to browse: it lists every free room matching the filters, for "is there a free
    room in building 8" or "find me a room for 4 people on Thursday" - leave building empty too to search
    every building and get a spread of options. Give room_id to check one specific room before booking: it
    says whether it can be booked and, if so, returns a check_id. Leave end empty if the student only gave
    a start time: the response assumes one hour and says so via end_assumed, so mention that assumption in
    one line rather than asking for an end time first. Only ask the student for a date and time if they
    gave neither at all - there is no tool for the current clock time, only get_current_week's date.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        date: The date as YYYY-MM-DD.
        start: The start time as HH:MM, 24 hour.
        end: Optional end time as HH:MM, 24 hour. Leave empty to assume one hour from start.
        building: Optional building number, for example 8, to only look there.
        party_size: Optional number of people, to only show rooms that fit them.
        room_id: Optional specific room, for example 8.5.12 (from a previous browse), to check just that one.

    Returns:
        found, the end time used and end_assumed (true when end was not given). Browsing: the matching free rooms. Checking one room: can_book, the room, reasons if it cannot be booked, a check_id when it can, a simulation notice and a source block. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    end_assumed = end is None
    end = end or rooms.default_end(start)
    data = load("study_spaces.json")
    if room_id:
        result = rooms.assess_booking(data["rooms"], data["bookings"], room_id, date, start, end, party_size or 1)
        return {"found": True, "date": date, "start": start, "end": end, "end_assumed": end_assumed, **result,
                "check_id": rooms.check_id(room_id, date, start, end, party_size or 1) if result["can_book"] else None,
                "simulation_notice": rooms.NOTICE, "source": source(data, "study_spaces.json")}
    free = rooms.available_rooms(data["rooms"], data["bookings"], date, start, end, building, party_size)
    return {"found": True, "date": date, "start": start, "end": end, "end_assumed": end_assumed,
            "rooms": [rooms.view(r) for r in free], "source": source(data, "study_spaces.json")}


@tool(permission=ToolPermission.READ_WRITE)
def book_room(context: AgentRun, room_id: str, date: str, start: str, end: str, party_size: int,
              check_id: str, student_confirmed: bool) -> dict:
    """Book a study room for the logged-in student. This is a simulation and the only action that changes anything.

    Call this only after check_room_availability said the room can be booked (room_id given), you showed
    the student a summary, and they clearly said yes in their latest message. Pass the same room_id, date,
    start, end and party_size, the check_id from check_room_availability, and student_confirmed true. If
    the student said no, or was unclear, do not call this. It refuses if the student has not confirmed, if
    the check_id does not match, or if the room is no longer available, and gives a coded error. Always
    tell the student the result and the simulation notice.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        room_id: The room that was checked, for example 8.5.12.
        date: The same date that was checked.
        start: The same start time that was checked.
        end: The same end time that was checked.
        party_size: The same party size that was checked.
        check_id: The check_id returned by check_room_availability for this room, date, time and party size.
        student_confirmed: True only if the student explicitly said yes in this conversation.

    Returns:
        status booked with a reference number and the room, or status refused with an error code (NOT_CONFIRMED, INVALID_CHECK, UNKNOWN_ROOM, PARTY_TOO_LARGE or ROOM_BUSY) and a one-line message, and a simulation notice. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    data = load("study_spaces.json")
    return rooms.book_response(data["rooms"], data["bookings"], room_id, date, start, end, party_size,
                               check_id, student_confirmed)
