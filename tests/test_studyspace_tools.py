import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import load
from tools.studyspace_tools import book_room, check_room_availability

# From data/study_spaces.json: 14.4.02 (building 14, capacity 8) is booked 13:00-15:00 on 2026-10-01
# (Thursday, in the project's demo week). 8.5.12 (building 8, capacity 6) is free that slot.
DATE = "2026-10-01"
BUSY_ROOM, BUSY_START, BUSY_END = "14.4.02", "13:00", "15:00"
FREE_ROOM = "8.5.12"


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def browse(**kwargs):
    kwargs.setdefault("context", ctx("S0000004"))
    return check_room_availability.fn(**kwargs)


def test_nobody_logged_in_is_reported_plainly():
    r = check_room_availability.fn(context=ctx(None), date=DATE, start="09:00", end="11:00")
    assert r["found"] is False and "logged in" in r["reason"]


def test_browsing_lists_only_free_rooms_that_fit():
    r = browse(date=DATE, start=BUSY_START, end=BUSY_END, building="14")
    ids = {room["room_id"] for room in r["rooms"]}
    assert BUSY_ROOM not in ids  # booked at this exact time
    assert "14.4.19" in ids  # the other building-14 room, free at this time


def test_browsing_filters_by_party_size():
    r = browse(date=DATE, start="09:00", end="11:00", party_size=10)
    assert all(room["capacity"] >= 10 for room in r["rooms"])
    assert r["rooms"]  # 8.10.02 and 80.4.06 seat 10+


def test_no_building_given_searches_every_building_for_a_spread():
    r = browse(date=DATE, start="09:00", end="11:00")
    assert len({room["building"] for room in r["rooms"]}) > 1


def test_end_omitted_assumes_one_hour_and_says_so():
    r = browse(date=DATE, start="10:00")
    assert r["end"] == "11:00" and r["end_assumed"] is True


def test_end_given_is_used_as_is_and_not_flagged_as_assumed():
    r = browse(date=DATE, start="10:00", end="12:30")
    assert r["end"] == "12:30" and r["end_assumed"] is False


def test_end_omitted_still_applies_when_checking_a_specific_room():
    r = browse(date=DATE, start="09:00", room_id=FREE_ROOM, party_size=2)
    assert r["end"] == "10:00" and r["end_assumed"] is True and r["can_book"] is True


def test_default_end_wraps_past_midnight():
    from tools.studyspaces import default_end
    assert default_end("23:30") == "00:30"
    assert default_end("10:00", hours=2) == "12:00"


def test_checking_a_specific_busy_room_refuses_with_no_check_id():
    r = browse(date=DATE, start=BUSY_START, end=BUSY_END, room_id=BUSY_ROOM, party_size=4)
    assert r["can_book"] is False and r["check_id"] is None
    assert r["reasons"][0]["code"] == "ROOM_BUSY"


def test_checking_a_room_too_small_for_the_party_refuses():
    r = browse(date=DATE, start="09:00", end="11:00", room_id="8.6.03", party_size=6)  # capacity 2
    assert r["can_book"] is False
    assert r["reasons"][0]["code"] == "PARTY_TOO_LARGE"


def test_an_unknown_room_is_reported_plainly():
    r = browse(date=DATE, start="09:00", end="11:00", room_id="9.9.99")
    assert r["can_book"] is False and r["reasons"][0]["code"] == "UNKNOWN_ROOM"


def test_checking_a_free_room_returns_a_usable_check_id():
    r = browse(date=DATE, start="15:00", end="17:00", room_id=FREE_ROOM, party_size=4)
    assert r["can_book"] is True and isinstance(r["check_id"], str) and len(r["check_id"]) == 16


def test_booking_without_confirmation_is_refused_and_changes_nothing():
    check = browse(date=DATE, start="15:00", end="17:00", room_id=FREE_ROOM, party_size=4)
    r = book_room.fn(context=ctx("S0000004"), room_id=FREE_ROOM, date=DATE, start="15:00", end="17:00",
                     party_size=4, check_id=check["check_id"], student_confirmed=False)
    assert r["status"] == "refused" and r["error"]["code"] == "NOT_CONFIRMED"


def test_booking_with_a_mismatched_check_id_is_refused():
    r = book_room.fn(context=ctx("S0000004"), room_id=FREE_ROOM, date=DATE, start="15:00", end="17:00",
                     party_size=4, check_id="wrong0000000000", student_confirmed=True)
    assert r["status"] == "refused" and r["error"]["code"] == "INVALID_CHECK"


def test_booking_a_free_room_with_confirmation_succeeds():
    check = browse(date=DATE, start="09:00", end="11:00", room_id="80.3.11", party_size=4)
    assert check["can_book"] is True
    r = book_room.fn(context=ctx("S0000004"), room_id="80.3.11", date=DATE, start="09:00", end="11:00",
                     party_size=4, check_id=check["check_id"], student_confirmed=True)
    assert r["status"] == "booked" and r["reference"].startswith("ROOM-") and r["simulated"] is True


def test_booking_is_simulated_and_does_not_persist():
    """Confirms the stateless design: booking a room does not add it to study_spaces.json's bookings, so
    a second check of the exact same slot still reports it as free."""
    before = load("study_spaces.json")["bookings"]
    check = browse(date=DATE, start="11:00", end="13:00", room_id="12.2.05", party_size=2)
    book_room.fn(context=ctx("S0000004"), room_id="12.2.05", date=DATE, start="11:00", end="13:00",
                party_size=2, check_id=check["check_id"], student_confirmed=True)
    after = load("study_spaces.json")["bookings"]
    assert before == after
    recheck = browse(date=DATE, start="11:00", end="13:00", room_id="12.2.05", party_size=2)
    assert recheck["can_book"] is True


def test_booking_a_now_busy_room_is_refused_even_with_a_valid_check_id():
    from tools import studyspaces as rooms
    cid = rooms.check_id(BUSY_ROOM, DATE, BUSY_START, BUSY_END, 4)
    r = book_room.fn(context=ctx("S0000004"), room_id=BUSY_ROOM, date=DATE, start=BUSY_START, end=BUSY_END,
                     party_size=4, check_id=cid, student_confirmed=True)
    assert r["status"] == "refused" and r["error"]["code"] == "ROOM_BUSY"
