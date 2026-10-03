"""Study plan logic: place the courses a student still needs in the earliest terms that work."""
from collections import defaultdict

from tools import programs as prog, scheduling as sch
from tools.common import load

PASS_MARK = 50
LECTURE_NOTE = "Choose any lecture option. Lectures are online with recordings."
SLOT_CREDIT_POINTS = 12


def load_label(cap: int, program: dict) -> str | None:
    return prog.study_load_label(program, cap)


def build_sequence(program: dict, courses: dict, done: set) -> list[tuple]:
    """What is left to place, in program order: ("compulsory", course_id) and ("option", pool, kind, credit points).

    Courses already done count towards the options and choices in program order, so the first slots are the ones
    that are filled.
    """
    counted: set = set()
    sequence = []
    for _, item in prog.items(program):
        if item["type"] == "course":
            if item["course_id"] not in done:
                sequence.append(("compulsory", item["course_id"]))
            continue
        pool = prog.pool(program, item)
        need = item["credit_points"]
        for c in pool:
            if need > 0 and c in done and c not in counted:
                counted.add(c)
                need -= courses[c]["credit_points"]
        if need > 0:
            sequence.append(("option", pool, item["type"], need))
    return sequence


def build_plan(student: dict, blocks, cap: int, start_term: str | None = None, preferred=()) -> dict:
    program = prog.program_for(student)
    courses = {c["course_id"]: c for c in load("courses.json")}
    terms = sch.all_terms()
    first_open = sch.first_open_term()
    wanted_start = start_term or student["start_term"]
    start = max(wanted_start, first_open)
    plan_terms = [t for t in terms if t >= start]

    passed = {r["course_id"] for r in student["results"] if r["mark"] >= PASS_MARK}
    in_progress = {e["course_id"] for e in student["current_enrolments"] if e["term"] < start}
    committed = [e for e in student["current_enrolments"] if e["term"] >= start]
    committed_ids = {e["course_id"] for e in committed}
    done = passed | in_progress | committed_ids

    sequence = build_sequence(program, courses, done)
    stage_of = prog.stage_of(program)
    order = prog.order_before(program)

    used = defaultdict(int)
    placed = {}
    entries = defaultdict(list)
    taken = defaultdict(list)
    for e in committed:
        offering = sch.get_offering(e["course_id"], e["term"])
        workshop = next(o for o in sch.components(offering)["workshop"] if o["class_id"] in e["class_ids"])
        used[e["term"]] += courses[e["course_id"]]["credit_points"]
        placed[e["course_id"]] = e["term"]
        if workshop["day"]:
            taken[e["term"]].append((workshop["day"], workshop["start"], workshop["end"]))
        entries[e["term"]].append({"course_id": e["course_id"], "committed": True, "workshop": sch.view(workshop), "fit": sch.fit(workshop, blocks)})

    def prerequisites_met(cid: str, term: str) -> bool:
        needed = list(courses[cid]["prerequisites"])
        return all(p in passed or p in in_progress or (p in placed and placed[p] < term) for p in needed)

    def ordered_after_predecessor(cid: str, term: str) -> bool:
        before = order.get(cid)
        return before is None or before in passed or before in in_progress or (before in placed and placed[before] <= term)

    def can_place(cid: str, term: str) -> bool:
        cp = courses[cid]["credit_points"]
        offering = sch.get_offering(cid, term)
        if offering is None or used[term] + cp > cap:
            return False
        if not (prerequisites_met(cid, term) and ordered_after_predecessor(cid, term)):
            return False
        if sch.offering_fit(offering, blocks)["can_attend"] == "no":
            return False
        planned = [x["course_id"] for x in entries[term] if not x.get("committed")]
        return sch.choose_workshops(term, planned + [cid], blocks, taken[term]) is not None

    def place(cid: str, term: str, kind: str, suggested: bool) -> None:
        used[term] += courses[cid]["credit_points"]
        placed[cid] = term
        entries[term].append({"course_id": cid, "kind": kind, "suggested": suggested, "committed": False})

    def why_not(cid: str) -> str:
        cp = courses[cid]["credit_points"]
        if cp > cap:
            return f"it needs {cp} credit points, more than the {cap} allowed in a semester"
        offered = [t for t in plan_terms if sch.get_offering(cid, t)]
        if not offered:
            return f"it is not offered in the terms left in the timetable (to {plan_terms[-1]})"
        reasons = {sch.offering_fit(sch.get_offering(cid, t), blocks)["reason"] for t in offered}
        blocked = [t for t in offered if sch.offering_fit(sch.get_offering(cid, t), blocks)["can_attend"] == "no"]
        if len(blocked) == len(offered):
            return "in every term it runs, " + "; ".join(sorted(reasons))
        blockers = [p for p in courses[cid]["prerequisites"] if p not in passed and p not in in_progress]
        before = order.get(cid)
        if before and before not in passed and before not in in_progress:
            blockers.append(before)
        for b in blockers:
            if b not in placed:
                return f"it needs {courses[b]['title']} first, which could not be placed"
        latest = max(blockers, key=lambda b: placed[b], default=None)
        if latest and placed[latest] >= plan_terms[-1]:
            return (f"it has to come after {courses[latest]['title']}, which is in {placed[latest]}, "
                    f"and the timetable ends at {plan_terms[-1]}")
        return "there is no term with room that avoids clashes and meets the prerequisites"

    unplaced = []
    wanted = [c for c in preferred if c in prog.option_pool(program) and c not in done]
    for step in sequence:
        if step[0] == "compulsory":
            cid = step[1]
            term = next((t for t in plan_terms if can_place(cid, t)), None)
            if term:
                place(cid, term, "compulsory", False)
            else:
                unplaced.append({"course_id": cid, "title": courses[cid]["title"], "reason": why_not(cid)})
            continue
        _, slot_pool, slot_kind, need = step
        while need > 0:
            pool = [c for c in slot_pool if c not in done and c not in placed]
            choice = None
            while choice is None and any(c in pool for c in wanted):
                pick = next(c for c in wanted if c in pool)
                wanted.remove(pick)
                term = next((t for t in plan_terms if can_place(pick, t)), None)
                if term:
                    choice = (pick, term, False)
                else:
                    unplaced.append({"course_id": pick, "title": courses[pick]["title"], "reason": why_not(pick), "your_choice": True})
            if choice is None:
                choice = next(((c, t, True) for t in plan_terms for c in pool if can_place(c, t)), None)
            if choice:
                place(choice[0], choice[1], slot_kind, choice[2])
                need -= courses[choice[0]]["credit_points"]
            else:
                unplaced.append({"course_id": None, "title": "an option course", "reason": "no option course fits your availability in the terms left"})
                need -= SLOT_CREDIT_POINTS

    semesters = []
    for term in sorted(entries):
        planned = [x["course_id"] for x in entries[term] if not x["committed"]]
        chosen = sch.choose_workshops(term, planned, blocks, taken[term]) if planned else {}
        rows = []
        for x in entries[term]:
            c = courses[x["course_id"]]
            workshop, fit_label = (x["workshop"], x["fit"]) if x["committed"] else (sch.view(chosen[x["course_id"]]), sch.fit(chosen[x["course_id"]], blocks))
            rows.append({
                "course_id": c["course_id"], "title": c["title"], "credit_points": c["credit_points"],
                "kind": "compulsory" if x["course_id"] in stage_of else ("choice" if x.get("kind") == "choice" else "option"),
                "stage": stage_of.get(x["course_id"]),
                "status": "already enrolled" if x["committed"] else "planned",
                "suggested_option": bool(x.get("suggested")),
                "workshop": {"class_id": workshop["class_id"], "when": workshop["when"], "fit": fit_label},
                "workshop_unconfirmed": fit_label == "unknown",
            })
        semesters.append({"term": term, "semester_number": terms.index(term) - terms.index(start) + 1,
                          "credit_points": sum(r["credit_points"] for r in rows), "courses": rows})

    span = terms.index(semesters[-1]["term"]) - terms.index(start) + 1 if semesters else 0
    label = load_label(cap, program)
    years_published = program["duration"].get(f"{label.replace('-', '_')}_years") if label else None
    started_fresh = not (passed or in_progress or committed_ids)
    note = None
    if started_fresh and years_published is not None and semesters and not unplaced:
        if span / 2 == years_published:
            note = f"This matches the published {label} duration of {years_published} year(s)."
        else:
            note = (f"This takes {span} semesters ({span / 2:g} years) but the published {label} duration is "
                    f"{years_published} year(s), because of prerequisites, the classes on offer and your availability.")
    flagged = [r["course_id"] for s in semesters for r in s["courses"] if r["workshop_unconfirmed"]]
    return {
        "start_term": start,
        "start_term_note": None if start == wanted_start else f"{wanted_start} is not open for enrolment, so the plan starts at {start}.",
        "credit_points_per_semester": cap, "load": label,
        "semesters": semesters, "semesters_needed": span, "years": span / 2 if span else 0,
        "published_duration_note": note,
        "complete": not unplaced, "unplaced": unplaced,
        "unconfirmed_workshops": flagged,
        "suggested_options": [r["course_id"] for s in semesters for r in s["courses"] if r["suggested_option"]],
        "already_passed": sorted(passed), "in_progress_assumed_passed": sorted(in_progress),
        "credit_points_planned": sum(s["credit_points"] for s in semesters),
        "lecture_note": LECTURE_NOTE,
    }
