"""Fixed-seed generator for the synthetic BH013 program, course, timetable and student data."""
import argparse
import hashlib
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 20260921
SNAPSHOT_DATE = "2026-09-21"
SEED_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SEED_DIR.parent / "data"

sys.path.insert(0, str(SEED_DIR.parent))
from planner.auth import hash_password  # noqa: E402
sys.path.insert(0, str(SEED_DIR))
from public import PUBLIC_PROGRAMS_FILE, PUBLIC_VALUES_FILE, load_public  # noqa: E402,F401

# S1 = February intake, S2 = July intake. 2026-S2 is the current term at the snapshot date.
# The first five terms are the original horizon. The rest let a six-year part-time degree be planned to the end.
ORIGINAL_TERMS = ["2026-S2", "2027-S1", "2027-S2", "2028-S1", "2028-S2"]
TERMS = ORIGINAL_TERMS + ["2029-S1", "2029-S2", "2030-S1", "2030-S2", "2031-S1", "2031-S2", "2032-S1", "2032-S2"]
CURRENT_TERM = TERMS[0]
TERM_STARTS = {
    "2026-S2": date(2026, 7, 20), "2027-S1": date(2027, 3, 1), "2027-S2": date(2027, 7, 19),
    "2028-S1": date(2028, 2, 28), "2028-S2": date(2028, 7, 17),
    "2029-S1": date(2029, 2, 26), "2029-S2": date(2029, 7, 16), "2030-S1": date(2030, 2, 25), "2030-S2": date(2030, 7, 15),
    "2031-S1": date(2031, 3, 3), "2031-S2": date(2031, 7, 21), "2032-S1": date(2032, 3, 1), "2032-S2": date(2032, 7, 19),
}

PUBLIC = "from_public_page"
SYNTHETIC = "synthetic"

# Synthetic prerequisites: both thesis courses need the compulsory Stage A courses.
# Part B does not need Part A, so a full-time student can finish in one year.
PREREQUISITES = {
    "COSC3154": ["COSC2148", "COSC2462"],
    "COSC3155": ["COSC2148", "COSC2462"],
}

# Synthetic prerequisites for the courses added with the Bachelor of Computer Science and Information Technology.
# Kept short and inside one program, so a student never needs a course their program does not contain.
NEW_PREREQUISITES = {
    "COSC2803": ["COSC2801"], "COSC2804": ["COSC2802"], "MATH2411": ["MATH2466"], "ISYS1118": ["COSC2803"],
    "COSC3106": ["COSC3103"], "COSC3046": ["COSC3103"], "COSC2759": ["COSC2757"], "ISYS1108": ["ISYS3413"],
    "COSC2536": ["COSC1111"], "INTE2628": ["INTE2627"], "INTE2629": ["INTE2628"],
    "COSC2821": ["COSC2757"], "COSC2824": ["COSC2757"], "COSC2829": ["COSC2821"], "COSC2349": ["COSC2348"],
    "COSC2815": ["COSC2738"], "COSC2816": ["COSC2738"], "COSC2818": ["COSC2816"],
    "COSC3100": ["COSC3099"], "COSC3101": ["COSC3100"], "COSC3102": ["COSC3101"],
    "COSC2758": ["COSC2391"], "COSC3091": ["COSC2758"], "COSC2309": ["COSC2391"], "COSC2471": ["COSC2391"],
    "ISYS3449": ["ISYS3446"], "COSC2384": ["COSC2385"], "COSC2382": ["COSC2384"], "COSC2383": ["COSC2382"],
    "ENVI1242": ["ENVI1241"], "INTE2688": ["INTE2687"], "COSC3157": ["COSC3156"],
}

# Fictional coordinators, assigned round robin. One course has none (missing-detail demo).
COORDINATORS = [
    ("Dr", "Imogen", "Falkner"), ("Prof", "Lena", "Ostrowe"), ("Dr", "Rohan", "Wexley"),
    ("Dr", "Tobias", "Marlowe"), ("Dr", "Priya", "Devlin"), ("Prof", "Marcus", "Halloran"),
    ("Dr", "Yuki", "Brandt"), ("Dr", "Alinta", "Corrigan"),
]
NO_COORDINATOR = "COSC3047"

# Lectures are assumed available online, so only workshops constrain availability.
# Slots: (label, day, start, end, mode). A student picks one option per component.
LECTURE_SLOTS = [
    ("tue_am", "Tue", "10:00", "12:00", "online"),
    ("thu_pm", "Thu", "13:00", "15:00", "online"),
]
DAY_WORKSHOPS = [
    ("mon_am", "Mon", "10:00", "12:00", "on_campus"),
    ("mon_pm", "Mon", "13:00", "15:00", "on_campus"),
    ("tue_am", "Tue", "10:00", "12:00", "on_campus"),
    ("tue_pm", "Tue", "14:00", "16:00", "on_campus"),
    ("wed_am", "Wed", "09:00", "11:00", "on_campus"),
    ("wed_pm", "Wed", "13:00", "15:00", "on_campus"),
    ("thu_pm", "Thu", "14:00", "16:00", "on_campus"),
    ("fri_am", "Fri", "10:00", "12:00", "on_campus"),
]
EVENING_WORKSHOPS = [
    ("mon_evening", "Mon", "18:00", "20:00", "on_campus"),
    ("tue_evening", "Tue", "18:00", "20:00", "on_campus"),
    ("wed_evening", "Wed", "18:00", "20:00", "on_campus"),
    ("thu_evening", "Thu", "18:00", "20:00", "on_campus"),
]

# Courses with an evening workshop, and the slot that is always offered. Compulsory and
# same-semester courses use different slots so a worker can attend both. The rest are
# daytime-only, which is the D2 situation (COSC2814 in particular).
EVENING_MUST = {
    "COSC2462": "tue_evening",
    "COSC2632": "wed_evening", "COSC2274": "thu_evening", "COSC1183": "mon_evening",
    "COSC2110": "mon_evening", "INTE2402": "tue_evening", "COSC2673": "wed_evening",
}

COSC2148_SPEC = {
    "lecture": {
        "pool": [
            ("wed_evening", "Wed", "17:30", "19:30", "online"),
            ("tue_day", "Tue", "13:00", "15:00", "online"),
        ],
        "must": ["wed_evening"],
        "count": (1, 2),
    },
    "workshop": {
        "pool": [
            ("mon_day", "Mon", "10:00", "12:00", "on_campus"),
            ("mon_evening", "Mon", "18:00", "20:00", "on_campus"),
            ("tue_day", "Tue", "15:00", "17:00", "on_campus"),
            ("wed_day", "Wed", "09:30", "11:30", "on_campus"),
            ("wed_evening", "Wed", "18:00", "20:00", "on_campus"),
            ("thu_day", "Thu", "13:00", "15:00", "on_campus"),
            ("thu_evening", "Thu", "18:30", "20:30", "online"),
            ("fri_day", "Fri", "10:00", "12:00", "on_campus"),
        ],
        "must": ["mon_evening"],
        "count": (2, 8),
    },
}
# Thesis: one seminar, and one supervisor-arranged workshop with no fixed time
THESIS_SPEC = {
    "lecture": {"pool": [("thu_evening", "Thu", "17:30", "19:30", "online")], "must": [], "count": (1, 1)},
    "workshop": {"pool": [("tbc", None, None, None, "online")], "must": [], "count": (1, 1)},
}

# Deliberate demo situations: (course, term, component, label)
THESIS_IDS = ("COSC3154", "COSC3155")
HERO_KEY = ("COSC2148", "2027-S1", "lecture", "wed_evening")
FULL_KEY = ("COSC2148", "2027-S2", "lecture", "wed_evening")
CLOSED_KEY = ("COSC2148", "2027-S2", "workshop", "mon_evening")
HERO_CLASS_ID = "1015"
# The hero term gets fixed option counts so the demo shows real choice
FIXED_COUNTS = {("COSC2148", "2027-S1"): {"lecture": 2, "workshop": 5}}


def program_course_ids(program: dict) -> list[str]:
    fixed = [i["course_id"] for s in program["stages"] for i in s["items"] if i["type"] == "course"]
    choices = [c for s in program["stages"] for i in s["items"] if i["type"] == "choice" for c in i["course_ids"]]
    named = [c for m in program.get("majors", []) + program.get("minors", []) for c in m["course_ids"]]
    return list(dict.fromkeys(fixed + choices + program["option_list"]["course_ids"] + named))


def course_order(pub: dict) -> list[str]:
    return list(dict.fromkeys(c for p in pub["programs"].values() for c in program_course_ids(p)))


def record(data: dict, public_fields: list[str], snapshot_date: str) -> dict:
    # Record-level provenance is synthetic whenever any field is synthetic
    return {
        **data,
        "provenance": SYNTHETIC,
        "field_provenance": {f: PUBLIC for f in public_fields},
        "snapshot_date": snapshot_date,
    }


STUDY_LOAD = {"full_time_cp_per_semester": 48, "part_time_cp_per_semester": 24}
ORDERED_PROGRAMS = {"BH013P26"}  # the Honours courses in a stage are taken in the order listed
PUBLIC_PROGRAM_KEYS = ["program_code", "title", "level", "duration", "intakes", "campus", "entry_score", "places", "total_credit_points",
                       "stages", "option_list", "majors", "minors", "majors_and_minors_note", "combinations"]


def build_program(p: dict, snapshot_date: str) -> dict:
    """One program record: the public structure plus our own fields (study load, ordering, credit point totals)."""
    stages = [{**s, "ordered": p["program_code"] in ORDERED_PROGRAMS} for s in p["stages"]]
    load = STUDY_LOAD if "part_time_years" in p["duration"] else {"full_time_cp_per_semester": 48}
    return record({**p, "study_load": load, "stages": stages,
                   "total_credit_points": sum(s["credit_points"] for s in p["stages"])},
                  [k for k in PUBLIC_PROGRAM_KEYS if k in p], snapshot_date)


def build_programs(pub: dict, snapshot_date: str) -> list[dict]:
    return [build_program(p, snapshot_date) for p in pub["programs"].values()]


# Synthetic directory of who a student can contact. Emails are fictional.
CONTACTS = [
    ("school_office", "School of Computing Technologies Office", "computing.office@example.invalid",
     "Questions about the program, courses, timetables, thesis and supervisors, and anything the assistant cannot answer.",
     ["program", "course", "timetable", "thesis", "supervisor", "class", "workshop", "lecture", "school", "prerequisite", "study plan"]),
    ("student_connect", "Student Connect (enrolment and records)", "student.connect@example.invalid",
     "Enrolment problems, results and academic record queries, changing or withdrawing from courses.",
     ["enrol", "withdraw", "results", "transcript", "record", "census", "discontinue"]),
    ("fees_and_payments", "Fees and Payments Team", "fees@example.invalid",
     "Fees, payments, HECS-HELP, refunds, overdue balances and account holds.",
     ["fee", "payment", "pay ", "hecs", "refund", "balance", "hold", "invoice", "overdue", "cost"]),
    ("international_student_office", "International Student Office", "international@example.invalid",
     "Visa conditions, study load rules and other matters for international students.",
     ["visa", "international", "coe", "study load", "immigration"]),
    ("equitable_learning_services", "Equitable Learning Services", "equitable.learning@example.invalid",
     "Disability, medical and other conditions that need study adjustments or equitable assessment arrangements.",
     ["disability", "adjustment", "equitable", "medical", "condition", "accessibility", "special consideration", "extension"]),
    ("student_support", "Student Support and Wellbeing", "student.support@example.invalid",
     "Counselling, wellbeing and personal support.",
     ["wellbeing", "counselling", "stress", "mental", "housing"]),
    ("scholarships_office", "Scholarships Office", "scholarships@example.invalid",
     "Scholarships, bursaries and financial support applications.",
     ["scholarship", "bursary", "grant", "financial support"]),
    ("credit_and_advanced_standing", "Credit and Advanced Standing Team", "credit@example.invalid",
     "Credit transfer and recognition of prior learning.",
     ["credit transfer", "credit", "recognition", "prior learning", "advanced standing", "exemption"]),
]


def build_contacts(snapshot_date: str) -> list[dict]:
    return [record({"team_id": tid, "name": name, "email": email, "use_for": use_for, "topics": topics}, [], snapshot_date)
            for tid, name, email, use_for, topics in CONTACTS]


def build_terms(pub: dict, snapshot_date: str) -> list[dict]:
    """Term calendar. Dates published by RMIT (in public_values.json) replace the synthetic estimates."""
    terms = []
    for term in TERMS:
        start = TERM_STARTS[term]

        def on(days: int) -> str:
            return (start + timedelta(days=days)).isoformat()

        published = pub["terms"].get(term, {})
        dates = {
            "start_date": start.isoformat(),
            "end_date": on(16 * 7 + 4),
            "enrolment_opens": on(-84),
            "enrolment_closes": on(14),
            "payment_due_date": on(21),
            "census_date": on(39),
        }
        dates.update(published)
        terms.append(record({"term": term, **dates}, list(published), snapshot_date))
    return terms


# First match wins, so the more specific phrases come first
CATEGORY_RULES = [
    ("deferred assessment period", "deferred_assessment_period"),
    ("assessment period", "assessment_period"),
    ("equitable assessment", "equitable_assessment_deadline"),
    ("results release", "results_release"),
    ("results released", "results_release"),
    ("census", "census"),
    ("add classes", "add_deadline"),
    ("drop classes", "drop_deadline"),
    ("withdraw from program", "withdraw_deadline"),
    ("classes begin", "classes_begin"),
    ("begins", "classes_begin"),
    ("classes resume", "classes_resume"),
    ("classes end", "classes_end"),
    ("semester break", "break"),
    ("orientation", "orientation"),
    ("enrolment opens", "enrolment_opens"),
    ("enrolment online opens", "enrolment_opens"),
    ("re-enrol", "re_enrolment_deadline"),
    ("graduat", "graduation"),
    ("public holiday", "holiday"),
    ("rmit holiday", "holiday"),
    ("new year", "holiday"),
    ("closed", "university_closure"),
    ("reopens", "university_reopens"),
    ("re-opens", "university_reopens"),
]


def categorise(event: str) -> str:
    text = event.lower()
    for phrase, category in CATEGORY_RULES:
        if phrase in text:
            return category
    raise ValueError(f"No category rule matches the event {event!r}")


def build_key_dates(pub: dict, snapshot_date: str) -> list[dict]:
    """One record per published calendar period. Dates and names are public; categories are our labels."""
    periods = []
    corrections = {(c["period"], c["event"]): c for c in pub["corrections"]}
    for period, source in pub["key_dates"].items():
        kind = {"S1": "semester", "S2": "semester", "SPR": "spring", "SUM": "summer"}[period.split("-")[1]]
        events = []
        for i, e in enumerate(source["events"], 1):
            category = categorise(e["event"])
            applies_to = None
            if category == "add_deadline":
                applies_to = "art_architecture_fashion_only" if e["event"].endswith("only") else "all_other_schools"
            event = {"id": f"{period}-{i:02d}", **e, "category": category, "applies_to": applies_to, "note": None}
            fix = corrections.pop((period, e["event"]), None)
            if fix:
                assert event[fix["field"]] == fix["published"], f"correction does not match the published {e['event']!r}"
                event[fix["field"]], event["note"] = fix["used"], fix["note"]
            events.append(event)
        periods.append(record({
            "period": period, "name": source["name"], "kind": kind, "weeks": source["weeks"], "events": events,
        }, ["weeks", "events"], snapshot_date))
    assert not corrections, f"corrections match no event: {list(corrections)}"
    return periods


def build_fees(snapshot_date: str) -> dict:
    """Simplified demo fees and rules by fee type. Not RMIT policy."""
    return record({
        "currency": "AUD",
        "fee_types": {
            "hecs_csp": {
                "label": "Commonwealth supported place (HECS-HELP)",
                "fee_per_12cp": 1800,
                "payment_options": ["defer_to_hecs_help", "pay_upfront"],
                "payment_rule": "No payment is due at enrolment. You can defer the fee with a HECS-HELP loan "
                                "and repay it later through the tax system, or pay upfront by the payment due date.",
                "withdrawal_rule": "Withdraw before the census date and you are not charged for the course "
                                   "and take on no loan debt for it.",
            },
            "domestic_full_fee": {
                "label": "Domestic full-fee place",
                "fee_per_12cp": 3600,
                "payment_options": ["pay_upfront"],
                "payment_rule": "The full fee is due by the payment due date for the term. "
                                "There is no loan option in this demo data.",
                "withdrawal_rule": "Withdraw before the census date for a full refund of the fee for that course.",
            },
            "international": {
                "label": "International student place",
                "fee_per_12cp": 5400,
                "payment_options": ["pay_upfront"],
                "payment_rule": "The full fee is due by the payment due date for the term and must be paid upfront. "
                                "No loan is available.",
                "withdrawal_rule": "Withdraw before the census date for a refund of the fee for that course. "
                                   "Changes to your study load may affect visa conditions: ask the international "
                                   "student office.",
            },
        },
    }, [], snapshot_date)


STUDY_SPACE_ROOMS = [
    ("8.5.12", "8", 5, 6, ["whiteboard", "monitor"]),
    ("8.6.03", "8", 6, 2, ["monitor"]),
    ("8.6.15", "8", 6, 4, ["whiteboard"]),
    ("8.7.08", "8", 7, 8, ["whiteboard", "monitor", "video_conference"]),
    ("8.9.21", "8", 9, 4, ["monitor"]),
    ("8.10.02", "8", 10, 10, ["whiteboard", "monitor", "video_conference"]),
    ("80.3.11", "80", 3, 6, ["whiteboard"]),
    ("80.3.24", "80", 3, 2, ["monitor"]),
    ("80.4.06", "80", 4, 12, ["whiteboard", "monitor", "video_conference"]),
    ("12.2.05", "12", 2, 4, ["whiteboard"]),
    ("12.2.18", "12", 2, 6, ["monitor"]),
    ("14.4.02", "14", 4, 8, ["whiteboard", "monitor"]),
    ("14.4.19", "14", 4, 2, []),
    ("100.1.03", "100", 1, 4, ["whiteboard"]),
]
# The current term's week containing the project's demo date - see assignment_plan()'s comment for why.
STUDY_SPACE_WEEK = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
STUDY_SPACE_SLOTS = [("09:00", "11:00"), ("11:00", "13:00"), ("13:00", "15:00"), ("15:00", "17:00")]


def build_study_spaces(snapshot_date: str) -> dict:
    """A room inventory and a pre-seeded set of other people's bookings, so "is there a free room right
    now" and "book a room for Thursday" both find a realistic mix of free and busy rooms around the
    project's demo date (28 September to 4 October 2026, which includes Thursday 1 October)."""
    rooms = [{"room_id": room_id, "building": building, "campus": "City Campus", "floor": floor,
              "capacity": capacity, "features": features}
             for room_id, building, floor, capacity, features in STUDY_SPACE_ROOMS]
    rng = random.Random(f"study_spaces:{snapshot_date}")
    seen, bookings = set(), []
    for day in STUDY_SPACE_WEEK:
        for _ in range(3):
            room_id = rng.choice(STUDY_SPACE_ROOMS)[0]
            start, end = rng.choice(STUDY_SPACE_SLOTS)
            key = (room_id, day, start)
            if key in seen:
                continue
            seen.add(key)
            bookings.append({"room_id": room_id, "date": day, "start": start, "end": end})
    bookings.sort(key=lambda b: (b["date"], b["room_id"], b["start"]))
    return record({"rooms": rooms, "bookings": bookings}, [], snapshot_date)


NO_ACCOUNT_ISSUES = {"balance_due": 0, "due_date": None, "hold": None}
OVERDUE_ACCOUNT = {
    "balance_due": 3600, "due_date": "2026-08-10",
    "hold": {"type": "unpaid_fees", "blocks": ["enrolment"],
             "message": "An overdue balance of 3600 AUD blocks new enrolments until it is paid."},
}


def build_students(offerings: list[dict], snapshot_date: str) -> list[dict]:
    def enrol(course_id, term, day=None, start=None, evening=False):
        """The first lecture plus the workshop (matched on day and start, or the first evening one, when asked)."""
        offering = next(o for o in offerings if (o["course_id"], o["term"]) == (course_id, term))
        comps = {c["component"]: c["options"] for c in offering["components"]}
        workshop = next(w for w in comps["workshop"]
                        if (evening and (w["start"] or "") >= "18:00") or (not evening and (day is None or (w["day"], w["start"]) == (day, start))))
        return {"course_id": course_id, "term": term,
                "class_ids": [comps["lecture"][0]["class_id"], workshop["class_id"]]}

    def result(course_id, term, mark):
        return {"course_id": course_id, "term": term, "mark": mark}

    def prior(title, institution, year, gpa):
        return {"title": title, "institution": institution, "year": year, "gpa": gpa}

    # One student per demo scenario. Results are whole-number marks out of 100.
    people = [
        ("Donovan Ong", "admitted_not_enrolled", "part_time", "2027-S1", "domestic", "hecs_csp",
         prior("Bachelor of Information Technology", "Synthetic University", 2025, 3.2), [], [], NO_ACCOUNT_ISSUES),
        ("Jordan Whitfield", "admitted_not_enrolled", "full_time", "2027-S1", "domestic", "domestic_full_fee",
         prior("Bachelor of Science (Computer Science)", "Example State University", 2025, 3.4), [], [], NO_ACCOUNT_ISSUES),
        ("Noor Halvorsen", "admitted_not_enrolled", "full_time", "2027-S1", "international", "international",
         prior("Bachelor of Computer Science", "Fictional Institute of Technology", 2025, 3.6), [], [], NO_ACCOUNT_ISSUES),
        ("Casey Delacroix", "enrolled", "part_time", "2026-S1", "domestic", "hecs_csp",
         prior("Bachelor of Software Engineering", "Synthetic University", 2024, 3.3),
         [result("COSC2148", "2026-S1", 78), result("COSC2462", "2026-S1", 85)],
         [enrol("COSC2110", "2026-S2", "Mon", "18:00"), enrol("COSC2673", "2026-S2", "Wed", "18:00")], NO_ACCOUNT_ISSUES),
        ("Morgan Ashby", "enrolled", "part_time", "2026-S1", "domestic", "hecs_csp",
         prior("Bachelor of Information Technology", "Example State University", 2024, 2.7),
         [result("COSC2148", "2026-S1", 55), result("COSC2462", "2026-S1", 42)],
         [enrol("COSC2462", "2026-S2", "Tue", "18:00"), enrol("COSC2633", "2026-S2")], NO_ACCOUNT_ISSUES),
        ("Taylor Nakamura", "enrolled", "full_time", "2025-S2", "domestic", "hecs_csp",
         prior("Bachelor of Computer Science", "Synthetic University", 2024, 3.8),
         [result("COSC2148", "2025-S2", 72), result("COSC2462", "2025-S2", 68), result("COSC2110", "2025-S2", 75),
          result("COSC2673", "2025-S2", 81), result("COSC3154", "2026-S1", 70), result("COSC2632", "2026-S1", 66)],
         [enrol("COSC3155", "2026-S2")], NO_ACCOUNT_ISSUES),
        ("Jamie Kowalczyk", "enrolled", "part_time", "2026-S1", "domestic", "domestic_full_fee",
         prior("Bachelor of Information Systems", "Fictional Institute of Technology", 2023, 2.9),
         [result("COSC2148", "2026-S1", 63), result("COSC2462", "2026-S1", 61)],
         [enrol("INTE2402", "2026-S2", "Tue", "18:00"), enrol("COSC2527", "2026-S2")], OVERDUE_ACCOUNT),
        ("Robin Achterberg", "enrolled", "part_time", "2027-S1", "domestic", "hecs_csp",
         prior("Bachelor of Data Science", "Example State University", 2025, 3.1), [],
         [enrol("COSC2148", "2027-S1", "Mon", "18:00"), enrol("COSC2462", "2027-S1", "Tue", "18:00")], NO_ACCOUNT_ISSUES),
        # Bachelor of Computer Science (BP094P23) and Bachelor of Information Technology (BP162P23)
        ("Kai Bellamy", "admitted_not_enrolled", "full_time", "2027-S1", "domestic", "hecs_csp", None, [], [], NO_ACCOUNT_ISSUES),
        ("Mika Torres", "enrolled", "part_time", "2024-S1", "domestic", "hecs_csp", None,
         [result("COSC2801", "2024-S1", 72), result("MATH2466", "2024-S1", 65), result("COSC2803", "2024-S2", 70),
          result("COSC2802", "2025-S1", 68), result("MATH2411", "2025-S1", 61), result("COSC2804", "2025-S2", 74),
          result("INTE2625", "2026-S1", 77), result("COSC2123", "2026-S1", 58)],
         [enrol("ISYS1118", "2026-S2", evening=True), enrol("COSC3045", "2026-S2", evening=True)], NO_ACCOUNT_ISSUES),
        ("Elliot Marchetti", "enrolled", "full_time", "2025-S1", "domestic", "hecs_csp", None,
         [result("COSC2801", "2025-S1", 75), result("MATH2466", "2025-S1", 68), result("COSC2802", "2025-S1", 71),
          result("INTE2625", "2025-S1", 80), result("COSC2803", "2025-S2", 66), result("COSC2804", "2025-S2", 73),
          result("MATH2411", "2026-S1", 62), result("COSC3045", "2026-S1", 70), result("COSC1111", "2026-S1", 77),
          result("ISYS1118", "2026-S1", 64)],
         [enrol("COSC2123", "2026-S2"), enrol("COSC2960", "2026-S2"), enrol("COSC2536", "2026-S2"), enrol("INTE2402", "2026-S2")],
         NO_ACCOUNT_ISSUES),
        ("Riley Okafor", "enrolled", "full_time", "2025-S2", "domestic", "hecs_csp", None,
         [result("COSC3109", "2025-S2", 70), result("INTE2625", "2025-S2", 64), result("COSC1111", "2025-S2", 48),
          result("COSC3103", "2025-S2", 72), result("COSC3106", "2026-S1", 66), result("COSC3046", "2026-S1", 59)],
         [enrol("COSC1111", "2026-S2"), enrol("COSC2757", "2026-S2"), enrol("COSC3088", "2026-S2"), enrol("ISYS3413", "2026-S2")],
         NO_ACCOUNT_ISSUES),
        ("Devon Ashworth", "admitted_not_enrolled", "full_time", "2027-S1", "international", "international", None, [], [], NO_ACCOUNT_ISSUES),
        ("Sasha Whitlock", "enrolled", "full_time", "2024-S1", "domestic", "hecs_csp", None,
         [result("COSC2801", "2024-S1", 70), result("MATH2466", "2024-S1", 66), result("COSC2802", "2024-S1", 68),
          result("INTE2625", "2024-S1", 74), result("COSC2803", "2024-S2", 72), result("COSC2804", "2024-S2", 65),
          result("MATH2411", "2025-S1", 60), result("COSC3045", "2025-S1", 71), result("ISYS1118", "2025-S1", 69),
          result("COSC2123", "2025-S1", 63), result("COSC2960", "2025-S2", 75), result("COSC1111", "2025-S2", 78),
          result("INTE2547", "2025-S2", 70), result("INTE2584", "2025-S2", 82), result("COSC2408", "2026-S1", 73),
          result("OENG1235", "2026-S1", 68), result("COSC2299", "2026-S1", 66), result("COSC2536", "2026-S1", 71)],
         [enrol("INTE2626", "2026-S2"), enrol("INTE2402", "2026-S2"), enrol("ISYS1079", "2026-S2"), enrol("COSC2276", "2026-S2")],
         NO_ACCOUNT_ISSUES),
    ]
    student_programs = ["BH013P26"] * 8 + ["BP094P23", "BP094P23", "BP094P23", "BP162P23", "BP162P23", "BP094P23"]
    students = []
    for i, (name, status, load, start, residency, fee, qualification, results, enrolments, account) in enumerate(people, 1):
        number = f"S{i:07d}"
        students.append(record({
            "student_number": number,
            "name": name,
            "email": f"{number.lower()}@example.invalid",
            "program_code": student_programs[i - 1],
            "enrolment_status": status,
            "study_load": load,
            "start_term": start,
            "residency": residency,
            "fee_type": fee,
            "prior_qualification": qualification,
            "results": results,
            "current_enrolments": enrolments,
            "account": account,
        }, [], snapshot_date))
    return students


CANVAS_ASSIGNMENT_TITLES = ["Assignment 1", "Assignment 2", "Assignment 3"]
CANVAS_ASSIGNMENTS_FILE = SEED_DIR / "canvas_assignments.json"
# For a course with no entry in CANVAS_ASSIGNMENTS_FILE: a name per sequence, and a summary using the course title.
CANVAS_FALLBACK = [
    ("Concepts and Exercises", "Work through exercises on the core concepts of {title} and explain your reasoning."),
    ("Applied Project", "Apply what you have learned in {title} to a small practical project and document your approach."),
    ("Final Project and Reflection", "Bring the semester's work in {title} together in a final project and reflect on what you learned."),
]


def canvas_assignment(names: dict, course: dict, sequence: int) -> dict:
    """The synthetic name and one-sentence summary of a course's assignment."""
    listed = names.get(course["course_id"])
    if listed:
        return listed[sequence - 1]
    name, summary = CANVAS_FALLBACK[sequence - 1]
    return {"name": name, "summary": summary.format(title=course["title"])}


def assignment_plan(term: str, snapshot_date: str) -> list[tuple[str, bool]]:
    """(due_date, submitted) for a term's three demo assignments.

    The current term's dates are anchored to its own start date, not the snapshot date, and deliberately
    spread so "what's due this week" and "did I submit assignment 2" stay meaningful for weeks around the
    project's demo date, not only on the day this data happened to be generated: assignment 1 is already
    graded, assignment 2 falls due in the week of 28 September to 4 October 2026 and is left unsubmitted
    (an overdue, still-open item worth asking about), and assignment 3 is safely in the future.
    """
    snap = date.fromisoformat(snapshot_date)
    if term == CURRENT_TERM:
        start = TERM_STARTS[CURRENT_TERM]
        plan = [(31, True), (70, False), (112, False)]
        return [((start + timedelta(days=o)).isoformat(), submitted) for o, submitted in plan]
    # A completed term: every assignment was due, and submitted, well before the snapshot date. The exact
    # historical date does not matter for a finished course; a per-term hash just keeps different terms
    # from landing on identical dates.
    jitter = int(hashlib.sha256(term.encode()).hexdigest(), 16) % 200
    return [((snap - timedelta(days=o + jitter)).isoformat(), True) for o in (400, 370, 340)]


def build_canvas(students: list[dict], courses: list[dict], snapshot_date: str) -> list[dict]:
    """One record per (student, course, term, assignment), for every course a student has a result or a
    current enrolment in. A student admitted but not yet enrolled in anything has none - correctly so."""
    known = {c["course_id"]: c for c in courses}
    names = json.loads(CANVAS_ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
    assignments = []
    for s in students:
        entries = [(r["course_id"], r["term"], r["mark"]) for r in s["results"]]
        entries += [(e["course_id"], e["term"], None) for e in s["current_enrolments"]]
        seen = set()
        for course_id, term, final_mark in entries:
            if course_id not in known or (course_id, term) in seen:
                continue
            seen.add((course_id, term))
            rng = random.Random(f"canvas:{s['student_number']}:{course_id}:{term}")
            for i, (due_date, submitted) in enumerate(assignment_plan(term, snapshot_date), 1):
                about = canvas_assignment(names, known[course_id], i)
                if not submitted:
                    mark = None
                elif final_mark is not None:
                    mark = max(0, min(100, final_mark + rng.choice([-4, -1, 0, 2, 3])))
                else:
                    mark = rng.randint(55, 92)
                assignments.append(record({
                    "student_number": s["student_number"],
                    "course_id": course_id,
                    "term": term,
                    "assignment_id": f"{s['student_number']}-{course_id}-{term}-A{i}",
                    "title": CANVAS_ASSIGNMENT_TITLES[i - 1],
                    "name": about["name"],
                    "summary": about["summary"],
                    "sequence": i,
                    "due_date": due_date,
                    "max_mark": 100,
                    "submitted": submitted,
                    "submitted_at": f"{due_date}T21:00:00+10:00" if submitted else None,
                    "mark": mark,
                    "feedback": ("Good work overall; see comments in Canvas." if mark is not None and mark >= 70
                                 else "Meets the requirements; see comments in Canvas." if mark is not None
                                 else None),
                }, [], snapshot_date))
    return assignments


def build_print_accounts(students: list[dict], snapshot_date: str) -> list[dict]:
    """A synthetic print credit balance per student, 0 to 25 AUD."""
    accounts = []
    for s in students:
        rng = random.Random(f"print:{s['student_number']}")
        accounts.append(record({
            "student_number": s["student_number"], "balance": round(rng.uniform(0, 25), 2), "currency": "AUD",
        }, [], snapshot_date))
    return accounts


CS_PROGRAMS = ["BH013P26", "BP094P23", "BP162P23"]
# (title, employer, type, location, relevant_programs, days_until_deadline, description). Empty
# relevant_programs means open to every program, not just computing. Employers are fictional.
CAREERS_LISTINGS = [
    ("Software Engineering Intern", "Fictional Corp", "internship", "Melbourne CBD", CS_PROGRAMS, 21,
     "Work on a small team shipping features for an internal web application. Some Python, some TypeScript."),
    ("Data Analyst Intern", "Synthetic Systems", "internship", "Melbourne CBD", CS_PROGRAMS, 35,
     "Clean and analyse operational datasets, build a couple of dashboards, present findings to the team."),
    ("Graduate Software Developer", "NorthWind Digital", "graduate", "Melbourne CBD", CS_PROGRAMS, 60,
     "A 12-month graduate program rotating through two product teams, with a mentor throughout."),
    ("IT Support Officer (Casual)", "Example State University", "casual", "Melbourne (multiple campuses)", [], 14,
     "Frontline IT support for staff and students: password resets, hardware loans, basic troubleshooting."),
    ("Machine Learning Intern", "Placeholder Analytics", "internship", "Remote (Australia)", CS_PROGRAMS, 45,
     "Support a small ML team building a recommendation model; requires Python and some statistics."),
    ("Cyber Security Graduate", "BrightPath Technologies", "graduate", "Melbourne CBD", ["BP094P23", "BP162P23"], 70,
     "Rotate through security operations, risk assessment and secure development over a two-year program."),
    ("Junior Web Developer (Part-time)", "Fictional Corp", "part_time", "Melbourne CBD", CS_PROGRAMS, 28,
     "10-15 hours a week maintaining a small client's website alongside study."),
    ("Business Analyst Intern", "Meridian Consulting Group", "internship", "Melbourne CBD", [], 50,
     "Support a consulting team gathering requirements and documenting processes for client projects."),
    ("Cloud Engineering Intern", "Synthetic Systems", "internship", "Melbourne CBD", CS_PROGRAMS, 40,
     "Help migrate internal tools to a cloud platform; exposure to CI/CD pipelines and infrastructure as code."),
    ("Library Student Assistant (Casual)", "Example State University", "casual", "Melbourne (City campus)", [], 10,
     "Shelving, circulation desk cover and helping students find resources, a few shifts a week."),
    ("Games Programming Intern", "Ninth Circle Interactive", "internship", "Melbourne CBD", ["BH013P26", "BP094P23"], 55,
     "Join a small indie studio building a prototype; C# and Unity experience helpful but not required."),
    ("IT Helpdesk Graduate", "Fictional Corp", "graduate", "Melbourne CBD", ["BP162P23"], 80,
     "A one-year rotation through service desk, systems administration and a small development team."),
    ("Marketing Assistant (Casual)", "BrightPath Technologies", "casual", "Melbourne CBD", [], 18,
     "Support the marketing team with social media scheduling and simple content edits, flexible hours."),
    ("Database Administration Intern", "Meridian Consulting Group", "internship", "Melbourne CBD", CS_PROGRAMS, 33,
     "Assist a DBA team with routine maintenance, backups and query performance tuning."),
    ("UX Research Intern", "NorthWind Digital", "internship", "Melbourne CBD", [], 25,
     "Support user interviews and usability testing for a redesign project; no coding required."),
    ("Network Engineering Graduate", "Placeholder Analytics", "graduate", "Melbourne CBD", CS_PROGRAMS, 90,
     "A structured graduate pathway toward a networking certification, working alongside senior engineers."),
    ("Retail Team Member (Casual)", "Southbank Outfitters", "casual", "Melbourne CBD", [], 7,
     "Weekend and evening shifts on the shop floor, no experience required."),
    ("Mobile App Developer Intern", "Ninth Circle Interactive", "internship", "Remote (Australia)", CS_PROGRAMS, 38,
     "Contribute to a small Flutter codebase, fixing bugs and building simple new screens."),
    ("Finance Graduate Program", "Meridian Consulting Group", "graduate", "Melbourne CBD", [], 100,
     "A two-year rotational program across financial planning, reporting and analysis."),
    ("DevOps Intern", "Synthetic Systems", "internship", "Melbourne CBD", CS_PROGRAMS, 42,
     "Support a platform team automating deployments and monitoring; some scripting experience expected."),
    ("Campus Ambassador (Casual)", "Example State University", "casual", "Melbourne (City campus)", [], 12,
     "Represent the university at open days and orientation events, a few hours a week during term."),
    ("Product Management Intern", "NorthWind Digital", "internship", "Melbourne CBD", [], 47,
     "Shadow a product manager, help write specs and run a small piece of the roadmap yourself."),
    ("Embedded Systems Intern", "Placeholder Analytics", "internship", "Melbourne CBD", CS_PROGRAMS, 65,
     "Work on firmware for a small IoT device, C and some Python for tooling."),
    ("Customer Support Officer (Casual)", "Fictional Corp", "casual", "Remote (Australia)", [], 9,
     "Answer customer tickets over chat and email, flexible casual hours."),
]


def build_careers_listings(snapshot_date: str) -> list[dict]:
    """A synthetic internships/jobs board, some open to every program and some tagged to computing
    programs, so search_internships has something relevant to find for any demo student."""
    snap = date.fromisoformat(snapshot_date)
    listings = []
    for i, (title, employer, kind, location, programs, days, description) in enumerate(CAREERS_LISTINGS, 1):
        listings.append(record({
            "listing_id": f"L{i:04d}",
            "title": title,
            "employer": employer,
            "type": kind,
            "location": location,
            "relevant_programs": programs,
            "deadline": (snap + timedelta(days=days)).isoformat(),
            "posted_date": (snap - timedelta(days=7)).isoformat(),
            "description": description,
        }, [], snapshot_date))
    return listings


LIBRARY_BOOKS = [
    ("Foundations of Algorithms", "R. Whitcombe"),
    ("Introduction to Machine Learning", "N. Okafor"),
    ("Database Systems: A Practical Approach", "L. Marchetti"),
    ("Computer Networks: Principles and Practice", "S. Halvorsen"),
    ("Software Engineering: A Modern Approach", "T. Achterberg"),
    ("Cloud Computing Fundamentals", "P. Kowalczyk"),
    ("Data Structures in Practice", "M. Delacroix"),
    ("Cybersecurity Essentials", "J. Bellamy"),
    ("Operating Systems Concepts", "A. Ashby"),
    ("Discrete Mathematics for Computing", "E. Nakamura"),
    ("Artificial Intelligence: A Modern Introduction", "C. Torres"),
    ("Human-Computer Interaction", "D. Ashworth"),
    ("Research Methods for Computing Students", "V. Whitlock"),
    ("Thesis Writing for Computer Science", "K. Okafor"),
    ("Project Management for Software Teams", "R. Bellamy"),
]
LOAN_PERIOD_DAYS = 21
MAX_RENEWALS = 2
# The one deliberate demo case: a loan another student has placed a hold on, so it cannot be renewed
# no matter how many renewals are left - a real library rule, not just the renewal cap.
ON_HOLD_LOAN = ("S0000006", 0)  # (student_number, index into that student's own loans)


def build_library_loans(students: list[dict], snapshot_date: str) -> list[dict]:
    """1-3 synthetic loans for each enrolled student; a student only admitted, not yet enrolled, has none
    - consistent with how canvas.json treats the same students."""
    snap = date.fromisoformat(snapshot_date)
    loans = []
    for s in students:
        if s["enrolment_status"] != "enrolled":
            continue
        rng = random.Random(f"library:{s['student_number']}")
        n = rng.randint(1, 3)
        books = rng.sample(LIBRARY_BOOKS, n)
        for i, (title, author) in enumerate(books):
            borrowed_offset = rng.randint(14, 56)
            borrowed = snap - timedelta(days=borrowed_offset)
            due = borrowed + timedelta(days=LOAN_PERIOD_DAYS)
            renewal_count = rng.choices([0, 1, MAX_RENEWALS], weights=[70, 20, 10])[0]
            on_hold = (s["student_number"], i) == ON_HOLD_LOAN
            loans.append(record({
                "student_number": s["student_number"],
                "loan_id": f"{s['student_number']}-L{i + 1}",
                "title": title,
                "author": author,
                "borrowed_date": borrowed.isoformat(),
                "due_date": due.isoformat(),
                "renewal_count": renewal_count,
                "on_hold_for_other": on_hold,
            }, [], snapshot_date))
    return loans


def build_accounts(students: list[dict], seed: int, snapshot_date: str) -> list[dict]:
    """Demo logins demo1..demoN, each with the password equal to the username, stored hashed."""
    accounts = []
    for i, student in enumerate(students, 1):
        username = f"demo{i}"
        salt = hashlib.sha256(f"{seed}:{username}".encode()).digest()[:16]
        accounts.append(record({
            "username": username,
            "student_number": student["student_number"],
            "salt": salt.hex(),
            "password_hash": hash_password(username, salt),
        }, [], snapshot_date))
    return accounts


def build_courses(pub: dict, snapshot_date: str) -> list[dict]:
    courses, synthetic_codes = [], 0
    for i, cid in enumerate(course_order(pub)):
        known = pub["courses"][cid]
        if "handbook_code" in known:
            handbook_code = known["handbook_code"]
        else:
            synthetic_codes += 1
            handbook_code = f"S{synthetic_codes:05d}"
        if cid == NO_COORDINATOR:
            coordinator = None
        else:
            title, first, last = COORDINATORS[i % len(COORDINATORS)]
            coordinator = {"name": f"{title} {first} {last}", "email": f"{first[0].lower()}.{last.lower()}@example.invalid"}
        courses.append(record({
            "course_id": cid,
            "handbook_code": handbook_code,
            "title": known["title"],
            "credit_points": known["credit_points"],
            "campus": known["campus"],
            "description": known.get(
                "description", f"Synthetic placeholder description for {known['title']}. Not taken from the RMIT Handbook."),
            "delivery_modes": known.get("delivery_modes", ["on_campus", "online"]),
            "assumed_knowledge": known.get("assumed_knowledge"),
            "prerequisites": PREREQUISITES.get(cid, NEW_PREREQUISITES.get(cid, [])),
            "coordinator": coordinator,
            **({"alternate_codes": known["alternate_codes"]} if "alternate_codes" in known else {}),
        }, ["course_id", *known], snapshot_date))
    return courses


def standard_spec(course_id: str, evening: dict | None = None) -> dict:
    must = EVENING_MUST.get(course_id) or (evening or {}).get(course_id)
    return {
        "lecture": {"pool": LECTURE_SLOTS, "must": [], "count": (1, 2)},
        "workshop": {
            "pool": DAY_WORKSHOPS + (EVENING_WORKSHOPS if must else []),
            "must": [must] if must else [],
            "count": (2, 8),
        },
    }


def course_spec(course_id: str, evening: dict) -> dict:
    if course_id == "COSC2148":
        return COSC2148_SPEC
    if course_id in THESIS_IDS:
        return THESIS_SPEC
    return standard_spec(course_id, evening)


def honours_courses(pub: dict) -> list[str]:
    return program_course_ids(pub["programs"]["BH013P26"])


def core_courses(pub: dict) -> set[str]:
    """Courses every student of a Bachelor program takes (fixed, or a choice of one). They run every term."""
    core = set()
    for code, p in pub["programs"].items():
        if code == "BH013P26":
            continue
        for stage in p["stages"]:
            for item in stage["items"]:
                if item["type"] == "course":
                    core.add(item["course_id"])
                elif item["type"] == "choice":
                    core.update(item["course_ids"])
    return core


def option_semesters(pub: dict) -> dict:
    """Option courses run one semester a year, alternating through their list. The Honours pattern is unchanged."""
    semesters = {cid: ("S1" if i % 2 == 0 else "S2")
                 for i, cid in enumerate(pub["programs"]["BH013P26"]["option_list"]["course_ids"])}
    original, core = set(honours_courses(pub)), core_courses(pub)
    others = [c for c in course_order(pub) if c not in original and c not in core]
    semesters.update({cid: ("S1" if i % 2 == 0 else "S2") for i, cid in enumerate(others)})
    return semesters


def evening_slots(pub: dict) -> dict[str, str]:
    """An evening workshop slot that is always offered: every core course, and every other option course."""
    original, core = set(honours_courses(pub)), core_courses(pub)
    slots = ["mon_evening", "tue_evening", "wed_evening", "thu_evening"]
    ordered = [c for c in course_order(pub) if c not in original]
    always = [c for i, c in enumerate(ordered) if c in core or i % 2 == 0]
    return {c: slots[i % 4] for i, c in enumerate(always)}


def pick_options(rng: random.Random, spec: dict, fixed: int | None = None) -> list[tuple]:
    pool, must = spec["pool"], spec["must"]
    low, high = spec["count"]
    n = min(fixed or rng.randint(low, high), len(pool))
    must_idx = [i for i, p in enumerate(pool) if p[0] in must]
    rest = [i for i in range(len(pool)) if i not in must_idx]
    chosen = must_idx + rng.sample(rest, max(0, n - len(must_idx)))
    return [pool[i] for i in sorted(chosen)]


def build_timetable(pub: dict, seed: int, snapshot_date: str) -> tuple[list[dict], dict]:
    offerings, demo = [], {}
    semesters, evening = option_semesters(pub), evening_slots(pub)
    order = course_order(pub)
    # Class numbers are given out in this order. The original courses and terms come first, so their numbers
    # do not change when programs or terms are added.
    original = honours_courses(pub)
    jobs = [(t, c) for t in ORIGINAL_TERMS for c in original]
    jobs += [(t, c) for t in TERMS for c in order if (t, c) not in set(jobs)]
    next_id = 1016
    for term, course_id in jobs:
        if course_id in semesters and not term.endswith(semesters[course_id]):
            continue
        components = []
        for component, spec in course_spec(course_id, evening).items():
            rng = random.Random(f"{seed}:{course_id}:{term}:{component}")
            options = []
            fixed = FIXED_COUNTS.get((course_id, term), {}).get(component)
            for label, day, start, end, mode in pick_options(rng, spec, fixed):
                key = (course_id, term, component, label)
                total = rng.choice([30, 40, 60, 80])
                taken = rng.randint(total // 3, total - 5)
                if key == HERO_KEY:
                    class_id, total, taken = HERO_CLASS_ID, 60, 41
                else:
                    class_id = str(next_id)
                    next_id += 1
                if key == FULL_KEY:
                    total, taken = 60, 60
                for name, k in [("hero", HERO_KEY), ("full", FULL_KEY), ("closed", CLOSED_KEY)]:
                    if key == k:
                        demo[name] = class_id
                options.append({
                    "class_id": class_id,
                    "day": day,
                    "start": start,
                    "end": end,
                    "mode": mode,
                    "campus": "City" if mode == "on_campus" else None,
                    "seats_total": total,
                    "seats_taken": taken,
                    "enrolment_open": key != CLOSED_KEY and term != CURRENT_TERM,
                })
            components.append({"component": component, "options": options})

        public = ["course_id"]
        if (course_id, term) == HERO_KEY[:2]:
            public.append(f"components.lecture.options.{HERO_CLASS_ID}.class_id")
        offerings.append(record(
            {"course_id": course_id, "term": term, "components": components}, public, snapshot_date,
        ))
    offerings.sort(key=lambda o: (TERMS.index(o["term"]), order.index(o["course_id"])))
    return offerings, demo


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--snapshot-date", default=SNAPSHOT_DATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pub = load_public()
    timetable, demo = build_timetable(pub, args.seed, args.snapshot_date)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "programs.json", build_programs(pub, args.snapshot_date))
    courses = build_courses(pub, args.snapshot_date)
    write_json(args.out / "courses.json", courses)
    write_json(args.out / "timetable.json", timetable)
    students = build_students(timetable, args.snapshot_date)
    write_json(args.out / "terms.json", build_terms(pub, args.snapshot_date))
    write_json(args.out / "key_dates.json", build_key_dates(pub, args.snapshot_date))
    write_json(args.out / "fees.json", build_fees(args.snapshot_date))
    write_json(args.out / "contacts.json", build_contacts(args.snapshot_date))
    write_json(args.out / "students.json", students)
    write_json(args.out / "accounts.json", build_accounts(students, args.seed, args.snapshot_date))
    canvas = build_canvas(students, courses, args.snapshot_date)
    write_json(args.out / "canvas.json", canvas)
    write_json(args.out / "study_spaces.json", build_study_spaces(args.snapshot_date))
    write_json(args.out / "print_accounts.json", build_print_accounts(students, args.snapshot_date))
    write_json(args.out / "careers_listings.json", build_careers_listings(args.snapshot_date))
    loans = build_library_loans(students, args.snapshot_date)
    write_json(args.out / "library_loans.json", loans)

    n_options = sum(len(c["options"]) for o in timetable for c in o["components"])
    print(f"Wrote 14 files to {args.out} ({len(timetable)} offerings, {n_options} options, "
          f"{len(students)} students, {len(canvas)} canvas assignments, {len(loans)} library loans, seed {args.seed})")
    print(f"Demo options: hero(open)={demo['hero']} full={demo['full']} closed={demo['closed']}")
    print("Demo courses: daytime-only=COSC2814, unmet prerequisite=COSC3154/COSC3155")


if __name__ == "__main__":
    main()
