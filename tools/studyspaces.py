"""Study room availability and booking. Nothing is stored: like dropping.py, the check id and the
reference number are derived from the booking itself, so book_room can verify a check without saved
state, and a room's "busy" status only ever reflects the rooms pre-seeded as booked, not any booking made
in this conversation.
"""
import hashlib

from tools.enrolment import SALT, problem

NOTICE = "SIMULATION: this is a demonstration. No real room has been booked, and all the data is synthetic."
DEFAULT_DURATION_HOURS = 1


def default_end(start: str, hours: int = DEFAULT_DURATION_HOURS) -> str:
    """start plus a default duration, for when the student gave a start time but not an end. Wraps past
    midnight if needed, unlikely as that is for a study room booking."""
    h, m = map(int, start.split(":"))
    total = (h * 60 + m + hours * 60) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _digest(room_id: str, date: str, start: str, end: str, party_size: int) -> str:
    return hashlib.sha256(f"{SALT}|room|{room_id}|{date}|{start}|{end}|{party_size}".encode()).hexdigest()


def check_id(room_id: str, date: str, start: str, end: str, party_size: int) -> str:
    return _digest(room_id, date, start, end, party_size)[:16]


def reference(room_id: str, date: str, start: str, end: str, party_size: int) -> str:
    return f"ROOM-{int(_digest(room_id, date, start, end, party_size)[:8], 16) % 1_000_000:06d}"


def overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


def is_free(room_id: str, date: str, start: str, end: str, bookings: list[dict]) -> bool:
    return not any(b["room_id"] == room_id and b["date"] == date and overlaps(start, end, b["start"], b["end"])
                   for b in bookings)


def view(room: dict) -> dict:
    return {"room_id": room["room_id"], "building": room["building"], "campus": room["campus"],
            "floor": room["floor"], "capacity": room["capacity"], "features": room["features"]}


def available_rooms(rooms: list[dict], bookings: list[dict], date: str, start: str, end: str,
                    building: str | None = None, party_size: int | None = None) -> list[dict]:
    candidates = [r for r in rooms if (not building or r["building"] == building)
                  and (not party_size or r["capacity"] >= party_size)]
    return [r for r in candidates if is_free(r["room_id"], date, start, end, bookings)]


def assess_booking(rooms: list[dict], bookings: list[dict], room_id: str, date: str, start: str, end: str,
                   party_size: int) -> dict:
    """Whether a specific room can be booked for this date, time and party size. Changes nothing."""
    room = next((r for r in rooms if r["room_id"] == room_id), None)
    if room is None:
        return {"can_book": False, "room": None, "reasons": [problem("UNKNOWN_ROOM", f"There is no room {room_id}.")]}
    reasons = []
    if party_size > room["capacity"]:
        reasons.append(problem("PARTY_TOO_LARGE", f"{room_id} seats {room['capacity']}, not {party_size}."))
    if not is_free(room_id, date, start, end, bookings):
        reasons.append(problem("ROOM_BUSY", f"{room_id} is already booked from {start} to {end} on {date}."))
    return {"can_book": not reasons, "room": view(room), "reasons": reasons}


def book_response(rooms: list[dict], bookings: list[dict], room_id: str, date: str, start: str, end: str,
                  party_size: int, cid: str, confirmed) -> dict:
    """What book_room returns: booked with a reference, or refused with a coded error. Changes nothing
    itself - a booking made here is not added to bookings, matching the stateless pattern the rest of
    this codebase uses by default (see tools/dropping.py)."""
    base = {"simulated": True, "notice": NOTICE}

    def refuse(code: str, message: str, **extra) -> dict:
        return {"status": "refused", "error": {"code": code, "message": message}, **extra, **base}

    if confirmed is not True:
        return refuse("NOT_CONFIRMED", "The student has not confirmed. Ask them to confirm and wait for a clear yes.")
    if cid != check_id(room_id, date, start, end, party_size):
        return refuse("INVALID_CHECK", "The check_id does not match this room, date, time and party size. "
                                       "Run check_room_availability with this room_id again.")
    result = assess_booking(rooms, bookings, room_id, date, start, end, party_size)
    if not result["can_book"]:
        first = result["reasons"][0]
        return refuse(first["code"], first["message"], all_reasons=result["reasons"])
    return {"status": "booked", "reference": reference(room_id, date, start, end, party_size),
            "room": result["room"], "date": date, "start": start, "end": end, "party_size": party_size, **base}
