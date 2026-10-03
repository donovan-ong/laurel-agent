"""Validate the generated data files (NFR-07). Exits 1 if any check fails."""
import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SEED_DIR))
from public import load_public  # noqa: E402
DATA_DIR = SEED_DIR.parent / "data"
DEFAULT_REPORT = SEED_DIR / "validation_report.txt"

PUBLIC = "from_public_page"
SYNTHETIC = "synthetic"
DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
COMPONENTS = ["lecture", "workshop"]
FILES = {
    "programs": "programs.json",
    "courses": "courses.json",
    "timetable": "timetable.json",
    "terms": "terms.json",
    "key_dates": "key_dates.json",
    "fees": "fees.json",
    "students": "students.json",
    "accounts": "accounts.json",
    "contacts": "contacts.json",
    "canvas": "canvas.json",
    "study_spaces": "study_spaces.json",
    "print_accounts": "print_accounts.json",
    "careers_listings": "careers_listings.json",
    "library_loans": "library_loans.json",
}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TERM = re.compile(r"^\d{4}-S[12]$")
STUDENT_NUMBER = re.compile(r"^S\d{7}$")
HEX = re.compile(r"^[0-9a-f]+$")
SYNTHETIC_HANDBOOK_CODE = re.compile(r"^S\d{5}$")
WEEKDAY_NOTE = re.compile(r"\((Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\)")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PERIOD_KINDS = ("semester", "spring", "summer")
ADD_SCOPES = ("art_architecture_fashion_only", "all_other_schools")
CATEGORIES = [
    "add_deadline", "assessment_period", "break", "census", "classes_begin", "classes_end", "classes_resume",
    "deferred_assessment_period", "drop_deadline", "enrolment_opens", "equitable_assessment_deadline",
    "graduation", "holiday", "orientation", "re_enrolment_deadline", "results_release",
    "university_closure", "university_reopens", "withdraw_deadline",
]
REQUIRED_CATEGORIES = ["classes_begin", "add_deadline", "census", "drop_deadline", "assessment_period", "results_release"]


def build_public_values(pub: dict) -> dict:
    """The only values that may be from_public_page (requirements 5.1), keyed by record."""
    values = {f"program:{code}": dict(p) for code, p in pub["programs"].items()}
    for cid, fields in pub["courses"].items():
        values[f"course:{cid}"] = {"course_id": cid, **fields}
        values[f"offering:{cid}"] = {"course_id": cid}
    for term, fields in pub["terms"].items():
        values[f"terms:{term}"] = dict(fields)
    for period, kd in pub["key_dates"].items():
        events = copy.deepcopy(kd["events"])
        for c in pub.get("corrections", []):
            for e in events if c["period"] == period else []:
                if e["event"] == c["event"] and e[c["field"]] == c["published"]:
                    e[c["field"]] = c["used"]
        values[f"key_dates:{period}"] = {"weeks": kd["weeks"], "events": events}
    for number, cid in pub["class_numbers"].items():
        for comp in COMPONENTS:
            values[f"offering:{cid}"][f"components.{comp}.options.{number}.class_id"] = number
    return values


PUBLIC_SOURCE = load_public()
PUBLIC_VALUES = build_public_values(PUBLIC_SOURCE)

MISSING = object()
PATH_KEYS = ("stage", "component", "class_id")


def load_data(data_dir: Path) -> dict:
    data = {}
    for key, name in FILES.items():
        path = Path(data_dir) / name
        try:
            data[key] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(f"{name} not found in {data_dir}") from None
        except json.JSONDecodeError as e:
            raise ValueError(f"{name} is not valid JSON: {e}") from None
    return data


def resolve(node, path: str):
    """Follow a dotted path; list items are matched on stage, component or class_id."""
    for part in path.split("."):
        if isinstance(node, list):
            node = next(
                (i for i in node if isinstance(i, dict) and any(i.get(k) == part for k in PATH_KEYS)),
                MISSING,
            )
        elif isinstance(node, dict):
            node = node.get(part, MISSING)
        else:
            return MISSING
        if node is MISSING:
            return MISSING
    return node


def records(data: dict):
    """Yield (label, public-values key, record) for every data record."""
    if isinstance(data["programs"], list):
        for p in data["programs"]:
            if isinstance(p, dict):
                yield f"programs.json[{p.get('program_code')}]", f"program:{p.get('program_code')}", p
    for c in data["courses"]:
        cid = c.get("course_id")
        yield f"courses.json[{cid}]", f"course:{cid}", c
    for o in data["timetable"]:
        cid = o.get("course_id")
        yield f"timetable.json[{cid} {o.get('term')}]", f"offering:{cid}", o
    for key, file, ident in [("students", "students.json", "student_number"), ("accounts", "accounts.json", "username"),
                             ("terms", "terms.json", "term"), ("key_dates", "key_dates.json", "period"),
                             ("contacts", "contacts.json", "team_id"), ("canvas", "canvas.json", "assignment_id"),
                             ("print_accounts", "print_accounts.json", "student_number"),
                             ("careers_listings", "careers_listings.json", "listing_id"),
                             ("library_loans", "library_loans.json", "loan_id")]:
        if isinstance(data[key], list):
            for r in data[key]:
                if isinstance(r, dict):
                    yield f"{file}[{r.get(ident)}]", f"{key}:{r.get(ident)}", r
    if isinstance(data["fees"], dict):
        yield "fees.json", "fees", data["fees"]
    if isinstance(data["study_spaces"], dict):
        yield "study_spaces.json", "study_spaces", data["study_spaces"]


def options(data: dict):
    """Yield (offering, component name, option) for every timetable option."""
    for o in data["timetable"]:
        for c in o["components"]:
            for opt in c["options"]:
                yield o, c["component"], opt


def fixed_course_ids(program: dict) -> list[str]:
    return [i["course_id"] for s in program["stages"] for i in s["items"] if i["type"] == "course"]


def choice_course_ids(program: dict) -> list[str]:
    return [c for s in program["stages"] for i in s["items"] if i["type"] == "choice" for c in i["course_ids"]]


def staged_course_ids(program: dict) -> list[str]:
    return fixed_course_ids(program) + choice_course_ids(program) + program["option_list"]["course_ids"]


def named_course_ids(program: dict) -> list[str]:
    return [c for kind in ("majors", "minors") for m in program.get(kind, []) for c in m["course_ids"]]


def program_of(d: dict, code: str) -> dict | None:
    return next((p for p in d["programs"] if p.get("program_code") == code), None)


def check_credit_points(d):
    errs = []
    cp = {c["course_id"]: c["credit_points"] for c in d["courses"]}
    for c in d["courses"]:
        if not isinstance(c["credit_points"], int) or c["credit_points"] <= 0:
            errs.append(f"{c['course_id']}: credit_points must be a positive integer")
    for p in d["programs"]:
        code = p["program_code"]
        needed = 0
        for s in p["stages"]:
            total = 0
            for i in s["items"]:
                if i["type"] == "course":
                    total += cp.get(i["course_id"], 0)
                else:
                    total += i["credit_points"]
                    needed += i["credit_points"]
                    pool = i["course_ids"] if i["type"] == "choice" else p["option_list"]["course_ids"]
                    if sum(cp.get(c, 0) for c in pool) < i["credit_points"]:
                        errs.append(f"{code} stage {s['stage']}: a {i['type']} item needs {i['credit_points']} cp but its courses offer fewer")
            if total != s["credit_points"]:
                errs.append(f"{code} stage {s['stage']}: items sum to {total} cp but the stage says {s['credit_points']}")
        stage_total = sum(s["credit_points"] for s in p["stages"])
        if p["total_credit_points"] != stage_total:
            errs.append(f"{code}: total_credit_points {p['total_credit_points']} does not match the stages ({stage_total})")
        available = sum(cp.get(i, 0) for i in p["option_list"]["course_ids"])
        if available < sum(i["credit_points"] for s in p["stages"] for i in s["items"] if i["type"] == "options"):
            errs.append(f"{code}: the option list offers {available} cp but the stages need more")
        for kind, size in (("majors", 96), ("minors", 48)):
            names = [m["name"] for m in p.get(kind, [])]
            errs += [f"{code}: duplicate {kind[:-1]} {n}" for n in sorted(set(names)) if names.count(n) > 1]
            for m in p.get(kind, []):
                where = f"{code} {kind[:-1]} {m['name']}"
                if m["credit_points"] != size:
                    errs.append(f"{where}: needs {m['credit_points']} cp but a {kind[:-1]} is {size}")
                if sum(g["credit_points"] for g in m["groups"]) != m["credit_points"]:
                    errs.append(f"{where}: its groups do not add up to {m['credit_points']} cp")
                if m["course_ids"] != [c for g in m["groups"] for c in g["course_ids"]]:
                    errs.append(f"{where}: course_ids does not match its groups")
                for g in m["groups"]:
                    if len(set(g["course_ids"])) != len(g["course_ids"]):
                        errs.append(f"{where}: a course is listed twice in a group")
                    if sum(cp.get(c, 0) for c in g["course_ids"]) < g["credit_points"]:
                        errs.append(f"{where}: a group needs {g['credit_points']} cp but lists fewer")
    return errs


def check_references(d):
    errs = []
    ids = [c["course_id"] for c in d["courses"]]
    known = set(ids)
    errs += [f"duplicate course_id {i}" for i in sorted(known) if ids.count(i) > 1]
    codes = [c["handbook_code"] for c in d["courses"]]
    errs += [f"duplicate handbook_code {i}" for i in sorted(set(codes)) if codes.count(i) > 1]
    for p in d["programs"]:
        code = p["program_code"]
        errs += [f"{code} references missing course {i}" for i in staged_course_ids(p) + named_course_ids(p) if i not in known]
        both = set(fixed_course_ids(p)) & set(p["option_list"]["course_ids"])
        errs += [f"{code}: {i} is both compulsory and on the option list" for i in sorted(both)]
    for c in d["courses"]:
        for pre in c["prerequisites"]:
            if pre not in known:
                errs.append(f"{c['course_id']} has prerequisite {pre}, which is not in courses.json")
            elif pre == c["course_id"]:
                errs.append(f"{c['course_id']} lists itself as a prerequisite")
    offered = set()
    for o in d["timetable"]:
        offered.add(o["course_id"])
        if o["course_id"] not in known:
            errs.append(f"timetable offering {o['term']} references missing course {o['course_id']}")
    for p in d["programs"]:
        errs += [f"{p['program_code']} course {i} has no timetable offering"
                 for i in sorted(set(staged_course_ids(p) + named_course_ids(p)) & known - offered)]
    codes_seen = {}
    for c in d["courses"]:
        for alt in c.get("alternate_codes", []):
            if alt["course_id"] in known:
                errs.append(f"{c['course_id']}: alternate code {alt['course_id']} is also a course of its own")
            if alt["course_id"] in codes_seen:
                errs.append(f"alternate code {alt['course_id']} is used by {codes_seen[alt['course_id']]} and {c['course_id']}")
            codes_seen[alt["course_id"]] = c["course_id"]
    terms = sorted({o["term"] for o in d["timetable"]})
    for p in d["programs"]:
        smallest = min(v for k, v in p["study_load"].items() if k.endswith("_cp_per_semester"))
        needed = -(-p["total_credit_points"] // smallest)
        starting = [t for t in terms if t >= "2027-S1"]
        if len(starting) < needed:
            errs.append(f"{p['program_code']}: the timetable has {len(starting)} terms from 2027-S1 but the slowest study load needs {needed}")
    return errs


def check_provenance(d):
    errs, dates = [], set()
    for label, _, r in records(d):
        prov = r.get("provenance")
        if prov is None:
            errs.append(f"{label}: missing provenance")
        elif prov not in (PUBLIC, SYNTHETIC):
            errs.append(f"{label}: provenance must be {PUBLIC} or {SYNTHETIC}, got {prov!r}")
        snap = r.get("snapshot_date")
        if snap is None:
            errs.append(f"{label}: missing snapshot_date")
        else:
            try:
                if not ISO_DATE.match(snap):
                    raise ValueError
                date.fromisoformat(snap)
                dates.add(snap)
            except (ValueError, TypeError):
                errs.append(f"{label}: snapshot_date {snap!r} is not an ISO date")
        for path, fp in r.get("field_provenance", {}).items():
            if fp not in (PUBLIC, SYNTHETIC):
                errs.append(f"{label}: field_provenance[{path}] must be {PUBLIC} or {SYNTHETIC}")
    if len(dates) > 1:
        errs.append(f"records use different snapshot dates: {sorted(dates)}")
    return errs


def matches_public(actual, public) -> bool:
    """Equal, except that list items may carry extra keys of our own (such as an event's category)."""
    if isinstance(public, list) and public and all(isinstance(p, dict) for p in public) and isinstance(actual, list):
        return len(actual) == len(public) and all(
            isinstance(a, dict) and all(a.get(k) == v for k, v in p.items()) for a, p in zip(actual, public))
    return actual == public


def check_public_values(d):
    errs = []
    for label, key, r in records(d):
        if r.get("provenance") == PUBLIC:
            errs.append(f"{label}: record-level {PUBLIC} not allowed; records hold synthetic values, so use {SYNTHETIC} with field_provenance")
        allowed = PUBLIC_VALUES.get(key, {})
        for path, fp in r.get("field_provenance", {}).items():
            if fp != PUBLIC:
                continue
            if path not in allowed:
                errs.append(f"{label}: {path} marked {PUBLIC} but is not listed in requirements 5.1")
                continue
            actual = resolve(r, path)
            if not matches_public(actual, allowed[path]):
                shown = "missing" if actual is MISSING else repr(actual)
                errs.append(f"{label}: {path} is {shown} but the public value is {allowed[path]!r}")
    for c in d["courses"]:
        if c.get("field_provenance", {}).get("handbook_code") != PUBLIC and not SYNTHETIC_HANDBOOK_CODE.match(c["handbook_code"]):
            errs.append(f"{c['course_id']}: handbook_code {c['handbook_code']!r} is not public, so it must be synthetic like S00001")
    return errs


def check_timetable(d):
    errs, seen_offerings, seen_ids = [], set(), set()
    for o in d["timetable"]:
        where = f"{o['course_id']} {o['term']}"
        if not TERM.match(o["term"]):
            errs.append(f"{where}: term must look like 2027-S1")
        if (o["course_id"], o["term"]) in seen_offerings:
            errs.append(f"{where}: duplicate offering")
        seen_offerings.add((o["course_id"], o["term"]))
        names = [c["component"] for c in o["components"]]
        if sorted(names) != sorted(COMPONENTS):
            errs.append(f"{where}: components must be exactly {COMPONENTS}, got {names}")
        for c in o["components"]:
            if not c["options"]:
                errs.append(f"{where}: {c['component']} has no options")
    for o, comp, opt in options(d):
        where = f"{o['course_id']} {o['term']} {comp} {opt['class_id']}"
        if opt["class_id"] in seen_ids:
            errs.append(f"{where}: duplicate class_id")
        seen_ids.add(opt["class_id"])
        if opt["mode"] not in ("on_campus", "online"):
            errs.append(f"{where}: mode must be on_campus or online")
        if comp == "lecture" and opt["mode"] != "online":
            errs.append(f"{where}: lecture mode must be online")
        if (opt["mode"] == "online") != (opt["campus"] is None):
            errs.append(f"{where}: campus must be null exactly when mode is online")
        when = [opt["day"], opt["start"], opt["end"]]
        if any(v is None for v in when):
            if not all(v is None for v in when):
                errs.append(f"{where}: day, start and end must all be set or all null")
        else:
            if opt["day"] not in DAYS:
                errs.append(f"{where}: unknown day {opt['day']!r}")
            if not (TIME.match(opt["start"]) and TIME.match(opt["end"])):
                errs.append(f"{where}: start and end must be HH:MM")
            elif opt["start"] >= opt["end"]:
                errs.append(f"{where}: start {opt['start']} is not before end {opt['end']}")
        total, taken = opt["seats_total"], opt["seats_taken"]
        if not (isinstance(total, int) and isinstance(taken, int) and total > 0 and 0 <= taken <= total):
            errs.append(f"{where}: seats_taken {taken} must be between 0 and seats_total {total}")
        if not isinstance(opt["enrolment_open"], bool):
            errs.append(f"{where}: enrolment_open must be true or false")
    return errs


def check_students(d):
    students = d["students"]
    if not isinstance(students, list) or not students:
        return ["students.json must be a non-empty list of students"]
    errs = []
    cp = {c["course_id"]: c["credit_points"] for c in d["courses"]}
    prereqs = {c["course_id"]: c["prerequisites"] for c in d["courses"]}
    offerings = {(o["course_id"], o["term"]): o for o in d["timetable"]}
    earliest = min(o["term"] for o in d["timetable"])
    fee_types = d["fees"]["fee_types"]
    numbers = [s["student_number"] for s in students]
    emails = [s["email"] for s in students]
    errs += [f"duplicate student_number {n}" for n in sorted(set(numbers)) if numbers.count(n) > 1]
    errs += [f"duplicate student email {e}" for e in sorted(set(emails)) if emails.count(e) > 1]
    for s in students:
        n = s["student_number"]
        if not STUDENT_NUMBER.match(n):
            errs.append(f"{n}: student_number must look like S0000001 (synthetic)")
        program = program_of(d, s["program_code"])
        if program is None:
            errs.append(f"{n}: program_code {s['program_code']} is not in programs.json")
            program = d["programs"][0]
        program_cp = program["total_credit_points"]
        if f"{s['study_load']}_cp_per_semester" not in program["study_load"]:
            errs.append(f"{n}: study_load {s['study_load']} is not offered in {program['program_code']}")
        if s["residency"] not in ("domestic", "international"):
            errs.append(f"{n}: residency must be domestic or international")
        if s["fee_type"] not in fee_types:
            errs.append(f"{n}: fee_type {s['fee_type']!r} is not in fees.json")
        elif (s["residency"] == "international") != (s["fee_type"] == "international"):
            errs.append(f"{n}: fee_type {s['fee_type']} does not match residency {s['residency']}")
        if s["enrolment_status"] not in ("prospective", "admitted_not_enrolled", "enrolled"):
            errs.append(f"{n}: unknown enrolment_status {s['enrolment_status']!r}")
        if s["study_load"] not in ("part_time", "full_time"):
            errs.append(f"{n}: unknown study_load {s['study_load']!r}")
        if not TERM.match(s["start_term"]):
            errs.append(f"{n}: start_term must look like 2027-S1")
        q = s["prior_qualification"]
        if q is not None and not (isinstance(q["gpa"], (int, float)) and 0 <= q["gpa"] <= 4 and round(q["gpa"], 1) == q["gpa"]):
            errs.append(f"{n}: prior_qualification gpa must be 0 to 4 with one decimal")

        seen, passed = set(), set()
        if not isinstance(s["results"], list):
            errs.append(f"{n}: results must be a list")
            continue
        for r in s["results"]:
            where = f"{n} result {r['course_id']} {r['term']}"
            if r["course_id"] not in cp:
                errs.append(f"{where}: unknown course")
            if not TERM.match(r["term"]) or r["term"] >= earliest:
                errs.append(f"{where}: result term must be a past term (before {earliest})")
            mark = r["mark"]
            if isinstance(mark, bool) or not isinstance(mark, int) or not 0 <= mark <= 100:
                errs.append(f"{where}: mark must be a whole number from 0 to 100")
            elif mark >= 50 and r["course_id"] in cp:
                passed.add(r["course_id"])
            if (r["course_id"], r["term"]) in seen:
                errs.append(f"{where}: duplicate result")
            seen.add((r["course_id"], r["term"]))

        enrolled_cp = 0
        for e in s["current_enrolments"]:
            where = f"{n} enrolment {e['course_id']} {e['term']}"
            offering = offerings.get((e["course_id"], e["term"]))
            if offering is None:
                errs.append(f"{where}: no such timetable offering")
                continue
            ids = {c["component"]: {o["class_id"] for o in c["options"]} for c in offering["components"]}
            chosen = e["class_ids"]
            if not (len(chosen) == 2 and len([i for i in chosen if i in ids["lecture"]]) == 1
                    and len([i for i in chosen if i in ids["workshop"]]) == 1):
                errs.append(f"{where}: class_ids must be one lecture option and one workshop option of the offering")
            errs += [f"{where}: prerequisite {p} not passed" for p in prereqs[e["course_id"]] if p not in passed]
            if e["course_id"] in passed:
                errs.append(f"{where}: course already passed")
            enrolled_cp += cp[e["course_id"]]
        if (s["enrolment_status"] == "enrolled") != bool(s["current_enrolments"]):
            errs.append(f"{n}: enrolment_status {s['enrolment_status']} does not match current_enrolments")
        if sum(cp[c] for c in passed) + enrolled_cp > program_cp:
            errs.append(f"{n}: passed plus enrolled credit points exceed the program total {program_cp}")

        acct = s["account"]
        if not isinstance(acct["balance_due"], (int, float)) or acct["balance_due"] < 0:
            errs.append(f"{n}: balance_due must be a non-negative number")
        if acct["due_date"] is not None and not ISO_DATE.match(acct["due_date"]):
            errs.append(f"{n}: account due_date must be an ISO date or null")
        hold = acct["hold"]
        if hold is not None:
            if not (hold.get("type") and isinstance(hold.get("blocks"), list) and hold.get("message")):
                errs.append(f"{n}: hold needs a type, a blocks list and a message")
            if not acct["balance_due"]:
                errs.append(f"{n}: a hold for unpaid fees needs a balance_due")
    return errs


def check_accounts(d):
    errs = []
    accounts, students = d["accounts"], d["students"]
    numbers = {s["student_number"] for s in students}
    usernames = [a["username"] for a in accounts]
    errs += [f"duplicate username {u}" for u in sorted(set(usernames)) if usernames.count(u) > 1]
    for a in accounts:
        who = a["username"]
        if a["student_number"] not in numbers:
            errs.append(f"account {who} maps to unknown student {a['student_number']}")
        if not (len(a["salt"]) == 32 and HEX.match(a["salt"]) and len(a["password_hash"]) == 64 and HEX.match(a["password_hash"])):
            errs.append(f"account {who}: salt must be 32 hex characters and password_hash 64 (a salted hash)")
        if "password" in a:
            errs.append(f"account {who}: plaintext password must not be stored")
    mapped = [a["student_number"] for a in accounts]
    errs += [f"student {n} has {mapped.count(n)} accounts, expected 1" for n in sorted(numbers) if mapped.count(n) != 1]
    return errs


def check_calendar_and_fees(d):
    errs = []
    terms = d["terms"]
    names = [t["term"] for t in terms]
    errs += [f"duplicate term {t} in terms.json" for t in sorted(set(names)) if names.count(t) > 1]
    errs += [f"timetable term {t} has no entry in terms.json" for t in sorted({o["term"] for o in d["timetable"]}) if t not in names]
    order = ["enrolment_opens", "start_date", "enrolment_closes", "payment_due_date", "census_date", "end_date"]
    for t in terms:
        try:
            dates = [date.fromisoformat(t[k]) for k in order]
        except (ValueError, TypeError):
            errs.append(f"{t['term']}: dates must be ISO dates")
            continue
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            errs.append(f"{t['term']}: dates must run {', '.join(order)} in order")
    fees = d["fees"]["fee_types"]
    for name, f in fees.items():
        if not (isinstance(f["fee_per_12cp"], (int, float)) and f["fee_per_12cp"] > 0):
            errs.append(f"fee type {name}: fee_per_12cp must be positive")
        if not (f["label"] and f["payment_options"] and f["payment_rule"] and f["withdrawal_rule"]):
            errs.append(f"fee type {name}: needs a label, payment options, a payment rule and a withdrawal rule")
    if not fees["hecs_csp"]["fee_per_12cp"] < fees["domestic_full_fee"]["fee_per_12cp"] < fees["international"]["fee_per_12cp"]:
        errs.append("fees must rise from hecs_csp to domestic_full_fee to international")
    return errs


def check_key_dates(d):
    errs, seen = [], set()
    periods = d["key_dates"]
    corrected = set()
    for c in PUBLIC_SOURCE.get("corrections", []):
        match = next((e for p in periods if p["period"] == c["period"] for e in p["events"] if e["event"] == c["event"]), None)
        if match is None:
            errs.append(f"correction for {c['period']} {c['event']!r} matches no event")
        elif match[c["field"]] != c["used"] or match["note"] != c["note"]:
            errs.append(f"{c['period']} {c['event']!r}: the correction ({c['field']} {c['used']}) is not applied with its note")
        else:
            corrected.add(match["id"])
    for p in periods:
        errs += [f"{p['period']} {e['id']}: has a note but no correction" for e in p["events"]
                 if e["note"] is not None and e["id"] not in corrected]
    ids = [p["period"] for p in periods]
    errs += [f"duplicate period {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for p in periods:
        who = p["period"]
        if p["kind"] not in PERIOD_KINDS:
            errs.append(f"{who}: kind must be one of {PERIOD_KINDS}")
        for e in p["events"]:
            where = f"{who} {e['id']}"
            if e["id"] in seen:
                errs.append(f"{where}: duplicate event id")
            seen.add(e["id"])
            try:
                start = date.fromisoformat(e["date"])
                end = date.fromisoformat(e["end_date"]) if e["end_date"] else start
            except (ValueError, TypeError):
                errs.append(f"{where}: date and end_date must be ISO dates")
                continue
            if end < start:
                errs.append(f"{where}: end_date is before date")
            if e["category"] not in CATEGORIES:
                errs.append(f"{where}: unknown category {e['category']!r}")
            if (e["category"] == "add_deadline") != (e["applies_to"] is not None) or e["applies_to"] not in (None, *ADD_SCOPES):
                errs.append(f"{where}: applies_to must be set, to a known scope, only on add deadlines")
            note = WEEKDAY_NOTE.search(e["event"])
            if note and DAY_NAMES[start.weekday()] != note.group(1):
                errs.append(f"{where}: weekday note says {note.group(1)} but {e['date']} is a {DAY_NAMES[start.weekday()]}")
        present = {e["category"] for e in p["events"]}
        errs += [f"{who}: no {c} event" for c in REQUIRED_CATEGORIES if c not in present]

        weeks = p["weeks"]
        if p["kind"] != "semester":
            if weeks:
                errs.append(f"{who}: only semesters have a week table")
            continue
        regular = [w for w in weeks if re.fullmatch(r"Week \d+", w["label"])]
        breaks = [w for w in weeks if w["label"] == "Mid-semester break"]
        if [w["label"] for w in regular] != [f"Week {i}" for i in range(1, 17)] or len(breaks) != 1:
            errs.append(f"{who}: weeks must be Week 1 to Week 16 with one Mid-semester break")
            continue
        try:
            spans = [(date.fromisoformat(w["start"]), date.fromisoformat(w["end"])) for w in regular]
            brk = (date.fromisoformat(breaks[0]["start"]), date.fromisoformat(breaks[0]["end"]))
        except (ValueError, TypeError):
            errs.append(f"{who}: week dates must be ISO dates")
            continue
        errs += [f"{who}: {w['label']} must span 7 days" for w, (a, b) in zip(regular, spans) if (b - a).days != 6]
        gaps = [(spans[i + 1][0] - spans[i][1]).days for i in range(15)]
        if sorted(gaps) != [1] * 14 + [8]:
            errs.append(f"{who}: weeks must run on, with one extra week for the mid-semester break")
        if not (spans[0][0] <= brk[0] <= brk[1] <= spans[-1][1]):
            errs.append(f"{who}: the Mid-semester break must fall inside the weeks")
        events_break = [(e["date"], e["end_date"]) for e in p["events"]
                        if e["category"] == "break" and "Mid-semester" in e["event"]]
        if events_break != [(breaks[0]["start"], breaks[0]["end"])]:
            errs.append(f"{who}: the Mid-semester break event {events_break} and the week table "
                        f"({breaks[0]['start']} to {breaks[0]['end']}) disagree")

    # The term calendar must agree with the published dates where both cover a term
    events = {p["period"]: p["events"] for p in periods}
    for t in d["terms"]:
        evs = events.get(t["term"])
        if not evs:
            continue

        def first(category, key, **where):
            match = next((e for e in evs if e["category"] == category and all(e[k] == v for k, v in where.items())), None)
            return match[key] if match else None

        for field, expected in [("start_date", first("classes_begin", "date")), ("census_date", first("census", "date")),
                                ("enrolment_closes", first("add_deadline", "date", applies_to="all_other_schools")),
                                ("end_date", first("assessment_period", "end_date"))]:
            if expected is not None and t[field] != expected:
                errs.append(f"terms.json {t['term']}: {field} {t[field]} does not match the key dates ({expected})")
    return errs


def check_contacts(d):
    errs = []
    ids = [c["team_id"] for c in d["contacts"]]
    errs += [f"duplicate team_id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    if "school_office" not in ids:
        errs.append("contacts must include school_office, the default recipient")
    for c in d["contacts"]:
        if not c["email"].endswith("@example.invalid"):
            errs.append(f"{c['team_id']}: contact email must end with @example.invalid (NFR-03)")
        if not (c["name"] and c["use_for"] and c["topics"] and all(isinstance(t, str) and t for t in c["topics"])):
            errs.append(f"{c['team_id']}: needs a name, a use_for text and a list of topics")
    return errs


def check_canvas(d):
    errs = []
    if not isinstance(d["canvas"], list):
        return ["canvas.json must be a list of assignment records"]
    students = {s["student_number"]: s for s in d["students"]}
    known_courses = {c["course_id"] for c in d["courses"]}
    ids = [a["assignment_id"] for a in d["canvas"]]
    errs += [f"duplicate assignment_id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for a in d["canvas"]:
        who = f"canvas.json[{a.get('assignment_id')}]"
        student = students.get(a["student_number"])
        if student is None:
            errs.append(f"{who}: unknown student {a['student_number']}")
            continue
        if a["course_id"] not in known_courses:
            errs.append(f"{who}: unknown course {a['course_id']}")
        has_result = any(r["course_id"] == a["course_id"] and r["term"] == a["term"] for r in student["results"])
        has_enrolment = any(e["course_id"] == a["course_id"] and e["term"] == a["term"]
                            for e in student["current_enrolments"])
        if not (has_result or has_enrolment):
            errs.append(f"{who}: {a['student_number']} has no result or current enrolment in {a['course_id']} {a['term']}")
        if not TERM.match(a["term"]):
            errs.append(f"{who}: term must look like 2026-S2")
        if not (isinstance(a.get("due_date"), str) and ISO_DATE.match(a["due_date"])):
            errs.append(f"{who}: due_date must be an ISO date")
        if a["title"] != f"Assignment {a['sequence']}":
            errs.append(f"{who}: title {a['title']!r} does not match sequence {a['sequence']}")
        if not (isinstance(a.get("name"), str) and a["name"].strip()):
            errs.append(f"{who}: name must be a non-empty string")
        summary = a.get("summary")
        if not (isinstance(summary, str) and summary.endswith(".") and len(summary) <= 160 and ". " not in summary):
            errs.append(f"{who}: summary must be one sentence of at most 160 characters")
        if a["submitted"]:
            if a["submitted_at"] is None:
                errs.append(f"{who}: submitted is true but submitted_at is null")
            if a["mark"] is not None and not (isinstance(a["mark"], int) and 0 <= a["mark"] <= a["max_mark"]):
                errs.append(f"{who}: mark must be a whole number from 0 to max_mark")
        elif a["submitted_at"] is not None or a["mark"] is not None:
            errs.append(f"{who}: not submitted, so submitted_at and mark must both be null")
    return errs


def check_study_spaces(d):
    errs = []
    ss = d["study_spaces"]
    if not isinstance(ss, dict) or not isinstance(ss.get("rooms"), list) or not isinstance(ss.get("bookings"), list):
        return ["study_spaces.json must be a dict with rooms and bookings lists"]
    room_ids = [r["room_id"] for r in ss["rooms"]]
    errs += [f"study_spaces.json: duplicate room_id {i}" for i in sorted(set(room_ids)) if room_ids.count(i) > 1]
    known_rooms = set(room_ids)
    for r in ss["rooms"]:
        who = f"study_spaces.json room[{r.get('room_id')}]"
        if not (isinstance(r.get("capacity"), int) and r["capacity"] > 0):
            errs.append(f"{who}: capacity must be a positive integer")
        if not r.get("building"):
            errs.append(f"{who}: building is required")
    for b in ss["bookings"]:
        who = f"study_spaces.json booking[{b.get('room_id')} {b.get('date')} {b.get('start')}]"
        if b.get("room_id") not in known_rooms:
            errs.append(f"{who}: unknown room {b.get('room_id')}")
        if not (isinstance(b.get("date"), str) and ISO_DATE.match(b["date"])):
            errs.append(f"{who}: date must be an ISO date")
        if not (isinstance(b.get("start"), str) and TIME.match(b["start"]) and isinstance(b.get("end"), str) and TIME.match(b["end"])):
            errs.append(f"{who}: start and end must be HH:MM")
        elif b["start"] >= b["end"]:
            errs.append(f"{who}: start {b['start']} is not before end {b['end']}")
    return errs


def check_print_accounts(d):
    errs = []
    accounts, students = d["print_accounts"], d["students"]
    numbers = {s["student_number"] for s in students}
    seen = [a["student_number"] for a in accounts]
    errs += [f"print_accounts.json: duplicate student {n}" for n in sorted(set(seen)) if seen.count(n) > 1]
    errs += [f"print_accounts.json: {n} has {seen.count(n)} print accounts, expected 1" for n in sorted(numbers) if seen.count(n) != 1]
    for a in accounts:
        who = f"print_accounts.json[{a.get('student_number')}]"
        if a["student_number"] not in numbers:
            errs.append(f"{who}: unknown student")
        if not (isinstance(a.get("balance"), (int, float)) and not isinstance(a["balance"], bool) and a["balance"] >= 0):
            errs.append(f"{who}: balance must be a non-negative number")
    return errs


LISTING_TYPES = ("internship", "graduate", "part_time", "casual")


def check_careers_listings(d):
    errs = []
    listings = d["careers_listings"]
    known_programs = {p["program_code"] for p in d["programs"]}
    ids = [l["listing_id"] for l in listings]
    errs += [f"careers_listings.json: duplicate listing_id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for l in listings:
        who = f"careers_listings.json[{l.get('listing_id')}]"
        if l.get("type") not in LISTING_TYPES:
            errs.append(f"{who}: type must be one of {LISTING_TYPES}")
        if not (l.get("title") and l.get("employer") and l.get("description")):
            errs.append(f"{who}: needs a title, an employer and a description")
        errs += [f"{who}: relevant_programs references unknown program {p}"
                 for p in l.get("relevant_programs", []) if p not in known_programs]
        for field in ("deadline", "posted_date"):
            if not (isinstance(l.get(field), str) and ISO_DATE.match(l[field])):
                errs.append(f"{who}: {field} must be an ISO date")
    return errs


MAX_RENEWALS = 2


def check_library_loans(d):
    errs = []
    loans, students = d["library_loans"], d["students"]
    numbers = {s["student_number"] for s in students}
    ids = [l["loan_id"] for l in loans]
    errs += [f"library_loans.json: duplicate loan_id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for l in loans:
        who = f"library_loans.json[{l.get('loan_id')}]"
        if l["student_number"] not in numbers:
            errs.append(f"{who}: unknown student {l['student_number']}")
        if not (l.get("title") and l.get("author")):
            errs.append(f"{who}: needs a title and an author")
        for field in ("borrowed_date", "due_date"):
            if not (isinstance(l.get(field), str) and ISO_DATE.match(l[field])):
                errs.append(f"{who}: {field} must be an ISO date")
        if l.get("due_date") and l.get("borrowed_date") and l["due_date"] <= l["borrowed_date"]:
            errs.append(f"{who}: due_date must be after borrowed_date")
        if not (isinstance(l.get("renewal_count"), int) and not isinstance(l["renewal_count"], bool)
                and 0 <= l["renewal_count"] <= MAX_RENEWALS):
            errs.append(f"{who}: renewal_count must be a whole number from 0 to {MAX_RENEWALS}")
        if not isinstance(l.get("on_hold_for_other"), bool):
            errs.append(f"{who}: on_hold_for_other must be true or false")
    if not any(l["renewal_count"] >= MAX_RENEWALS for l in loans):
        errs.append(f"no loan at the {MAX_RENEWALS}-renewal limit (needed for AT_RENEWAL_LIMIT)")
    if not any(l["on_hold_for_other"] for l in loans):
        errs.append("no loan on hold for another student (needed for ON_HOLD_FOR_ANOTHER_STUDENT)")
    return errs


def check_privacy(d):
    errs = []
    for c in d["courses"]:
        coord = c.get("coordinator")
        if coord and not coord["email"].endswith("@example.invalid"):
            errs.append(f"{c['course_id']}: coordinator email must end with @example.invalid (NFR-03)")
    for st in d["students"]:
        if not st["email"].endswith("@example.invalid"):
            errs.append(f"{st['student_number']}: student email must end with @example.invalid (NFR-03)")
    return errs


def is_daytime(opt) -> bool:
    return opt["day"] is not None and opt["start"] >= "09:00" and opt["end"] <= "17:00"


def is_evening(opt) -> bool:
    return opt["day"] is not None and opt["end"] > "17:00"


def check_demo_cases(d):
    """The deliberate demo situations (requirements 5.3) must exist."""
    errs = []
    opts = list(options(d))
    if not any(opt["seats_taken"] >= opt["seats_total"] for _, _, opt in opts):
        errs.append("no full option (needed for CLASS_FULL)")
    if not any(not opt["enrolment_open"] for _, _, opt in opts):
        errs.append("no option with enrolment_open false (needed for ENROLMENT_CLOSED)")
    if not any(opt["day"] is None for _, _, opt in opts):
        errs.append("no option with an unknown time (needed for unconfirmed plan items)")
    if not any(opt["class_id"] == "1015" for _, _, opt in opts):
        errs.append("hero class 1015 is missing")
    if not any(c["prerequisites"] for c in d["courses"]):
        errs.append("no course with a prerequisite (needed for PREREQUISITE_NOT_MET)")
    if not any(c["coordinator"] is None for c in d["courses"]):
        errs.append("no course with a missing coordinator (needed for missing-detail answers)")

    students = d["students"]
    cp = {c["course_id"]: c["credit_points"] for c in d["courses"]}
    earliest = min(o["term"] for o in d["timetable"])

    def passed_cp(s):
        return sum(cp[r["course_id"]] for r in s["results"] if r["mark"] >= 50)

    if {s["fee_type"] for s in students} != {"hecs_csp", "domestic_full_fee", "international"}:
        errs.append("students must cover all three fee types (needed for D5)")
    if not any(not s["results"] and s["enrolment_status"] == "admitted_not_enrolled" for s in students):
        errs.append("no new student with no results and no enrolments")
    if not any(any(r["mark"] < 50 for r in s["results"]) for s in students):
        errs.append("no student with a failed course")
    if not any(s["account"]["hold"] for s in students):
        errs.append("no student with an account hold")
    if not any(s["results"] and s["current_enrolments"] for s in students):
        errs.append("no continuing student with results and current enrolments")
    if not any(passed_cp(s) + sum(cp[e["course_id"]] for e in s["current_enrolments"]) == (program_of(d, s["program_code"]) or d["programs"][0])["total_credit_points"]
               for s in students):
        errs.append("no student in their final semester")
    if not any(e["term"] > earliest for s in students for e in s["current_enrolments"]):
        errs.append("no student already enrolled for a future term")

    try:
        snapshot = date.fromisoformat(d["programs"][0]["snapshot_date"])
    except (ValueError, TypeError):
        snapshot = None  # the provenance check reports a bad snapshot date
    if snapshot and not any(date.fromisoformat(w["start"]) <= snapshot <= date.fromisoformat(w["end"])
                            for p in d["key_dates"] for w in p["weeks"] if w["label"].startswith("Week")):
        errs.append("no teaching week covers the snapshot date (needed for 'what week is it')")

    workshops = {}
    for o, comp, opt in opts:
        if comp == "workshop":
            workshops.setdefault(o["course_id"], []).append((o["term"], opt))
    if not any(all(is_daytime(x) for _, x in opts_) for opts_ in workshops.values()):
        errs.append("no course whose workshops are all daytime (needed for D2)")

    # A 9-5 worker needs evening workshops for the compulsory courses and some option courses in every term
    program = program_of(d, "BH013P26") or d["programs"][0]
    option_ids = set(program["option_list"]["course_ids"])
    compulsory_a = [i["course_id"] for i in program["stages"][0]["items"] if i["type"] == "course"]
    for term in sorted({o["term"] for o in d["timetable"]}):
        evening = {cid for cid, opts_ in workshops.items() if any(t == term and is_evening(x) for t, x in opts_)}
        if len(evening & option_ids) < 2:
            errs.append(f"{term}: fewer than 2 option courses have an evening workshop (needed for D1)")
        errs += [f"{term}: {cid} has no evening workshop (needed for D1)" for cid in compulsory_a if cid not in evening]
    return errs


CHECKS = [
    ("stage and course credit points", check_credit_points),
    ("course references", check_references),
    ("provenance and snapshot_date", check_provenance),
    ("public values match requirements 5.1", check_public_values),
    ("timetable structure", check_timetable),
    ("students and results", check_students),
    ("accounts", check_accounts),
    ("term calendar and fees", check_calendar_and_fees),
    ("contacts", check_contacts),
    ("canvas assignments", check_canvas),
    ("study spaces", check_study_spaces),
    ("print accounts", check_print_accounts),
    ("careers listings", check_careers_listings),
    ("library loans", check_library_loans),
    ("key dates", check_key_dates),
    ("privacy (synthetic identities)", check_privacy),
    ("demo cases present", check_demo_cases),
]


def run_checks(data: dict) -> list[tuple[str, list[str]]]:
    results = []
    for name, fn in CHECKS:
        try:
            errs = fn(data)
        except (KeyError, TypeError, AttributeError, IndexError, ValueError, StopIteration) as e:
            errs = [f"check could not run, data is malformed ({type(e).__name__}: {e})"]
        results.append((name, errs))
    return results


def validate(data: dict) -> list[str]:
    return [e for _, errs in run_checks(data) for e in errs]


def render_report(data: dict) -> tuple[str, bool]:
    results = run_checks(data)
    first = data["programs"][0] if isinstance(data["programs"], list) and data["programs"] and isinstance(data["programs"][0], dict) else {}
    snap = first.get("snapshot_date", "unknown")
    n_err = sum(len(errs) for _, errs in results)
    lines = [f"Data validation (snapshot {snap})"]
    for name, errs in results:
        lines.append(f"{'FAIL' if errs else 'PASS'}  {name}")
        lines += [f"        - {e}" for e in errs]
    lines.append(f"Result: {'FAIL' if n_err else 'PASS'} ({len(results)} checks, {n_err} errors)")
    return "\n".join(lines) + "\n", n_err == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    parser.add_argument("--report", nargs="?", const=DEFAULT_REPORT, type=Path,
                        help="also write the output to a file (default seed/validation_report.txt)")
    args = parser.parse_args()
    try:
        data = load_data(args.data)
    except ValueError as e:
        print(f"FAIL  {e}")
        return 1
    text, ok = render_report(data)
    print(text, end="")
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
