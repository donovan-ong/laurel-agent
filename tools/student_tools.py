from typing import List, Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog
from tools.common import current_student, gpa, grade_for, load, not_found, source, strip_meta, wam

PASS_MARK = 50


@tool(permission=ToolPermission.READ_ONLY)
def get_student_profile(context: AgentRun) -> dict:
    """Get the profile of the student who is logged in: name, enrolment status, study load, start term, residency, fee type, prior qualification, current enrolments and any account hold.

    Use this first in every conversation, and whenever the student asks about their own details. It needs no input because the student is already logged in, and it never returns anyone else.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.

    Returns:
        found, the student's profile and a source block with provenance, snapshot date and file. If nobody is logged in, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    courses = {c["course_id"]: c for c in load("courses.json")}
    fields = ("student_number", "name", "email", "program_code", "enrolment_status", "study_load",
              "start_term", "residency", "fee_type", "prior_qualification")
    profile = {k: student[k] for k in fields}
    profile["current_enrolments"] = [{**e, "title": courses[e["course_id"]]["title"]} for e in student["current_enrolments"]]
    profile["account_hold"] = student["account"]["hold"]
    return {"found": True, "student": profile, "source": source(student, "students.json")}


@tool(permission=ToolPermission.READ_ONLY)
def get_academic_record(context: AgentRun) -> dict:
    """Get the logged-in student's results: each course with its mark out of 100 and grade, credit points passed, GPA on a 0 to 4 scale and WAM, both to one decimal.

    Use this when the student asks about their marks, grades, GPA, WAM, passed or failed courses, or progress so far. GPA and WAM count every result, failed courses included. Both are null when there are no results yet.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.

    Returns:
        found, the results, credit points passed, GPA, WAM, counts of passed and failed courses, the prior qualification and a source block. If nobody is logged in, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    courses = {c["course_id"]: c for c in load("courses.json")}
    credit_points = {cid: c["credit_points"] for cid, c in courses.items()}
    results = [{"course_id": r["course_id"], "title": courses[r["course_id"]]["title"], "term": r["term"],
                "credit_points": credit_points[r["course_id"]], "mark": r["mark"], "grade": grade_for(r["mark"]),
                "passed": r["mark"] >= PASS_MARK} for r in student["results"]]
    return {
        "found": True,
        "results": results,
        "credit_points_passed": sum(r["credit_points"] for r in results if r["passed"]),
        "courses_passed": sum(r["passed"] for r in results),
        "courses_failed": sum(not r["passed"] for r in results),
        "gpa": gpa(student["results"], credit_points),
        "gpa_scale": "0 to 4, one decimal",
        "wam": wam(student["results"], credit_points),
        "wam_scale": "0 to 100, one decimal",
        "prior_qualification": student["prior_qualification"],
        "source": source(student, "students.json"),
    }


@tool(permission=ToolPermission.READ_ONLY)
def get_fees(context: AgentRun, course_ids: Optional[List[str]] = None) -> dict:
    """Get the logged-in student's fees: their fee type explained, the fee per course, an estimate for chosen courses, how to pay, and their account balance, due date and any hold.

    Use this for questions about cost, paying, HECS-HELP, full fees, international fees, refunds or overdue balances. Pass course_ids to estimate the fee for those courses. whole_degree already gives the cost of the whole program (its compulsory courses and its option courses), so quote it for "what would the degree cost". It also lists every fee type so differences can be explained. Figures are synthetic demo values, not RMIT policy.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        course_ids: Optional course codes to estimate the fee for, for example a plan's courses.

    Returns:
        found, the student's fee type with its fee per 12 credit points, payment options and rules, an estimate if course_ids were given, the account, all fee types, and source blocks. If nobody is logged in, found is false with a reason.
    """
    student, error = current_student(context)
    if error:
        return error
    fees = load("fees.json")
    fee_type = fees["fee_types"][student["fee_type"]]
    courses = {c["course_id"]: c for c in load("courses.json")}
    program = prog.program_for(student)
    compulsory = prog.compulsory_ids(program)
    compulsory_cp = sum(courses[c]["credit_points"] for c in compulsory)
    option_cp = prog.free_credit_points(program)
    rate = fee_type["fee_per_12cp"]
    response = {
        "found": True,
        "fee_type": student["fee_type"],
        "fee_type_label": fee_type["label"],
        "currency": fees["currency"],
        "fee_per_12cp": fee_type["fee_per_12cp"],
        "payment_options": fee_type["payment_options"],
        "payment_rule": fee_type["payment_rule"],
        "withdrawal_rule": fee_type["withdrawal_rule"],
        "account": student["account"],
        "whole_degree": {
            "credit_points": program["total_credit_points"], "fee": rate * program["total_credit_points"] / 12,
            "compulsory": {"courses": len(compulsory), "credit_points": compulsory_cp, "fee": rate * compulsory_cp / 12},
            "options": {"courses": option_cp // 12, "credit_points": option_cp, "fee": rate * option_cp / 12},
            "note": "The whole program at this student's fee rate, before any credit or courses already passed.",
        },
        "all_fee_types": fees["fee_types"],
        "source": source(fees, "fees.json"),
        "account_source": source(student, "students.json"),
    }
    if course_ids:
        known = [courses[c] for c in course_ids if c in courses]
        lines = [{"course_id": c["course_id"], "title": c["title"], "credit_points": c["credit_points"],
                  "fee": fee_type["fee_per_12cp"] * c["credit_points"] / 12} for c in known]
        response["estimate"] = {
            "courses": lines,
            "total": sum(line["fee"] for line in lines),
            "unknown_course_ids": [c for c in course_ids if c not in courses],
        }
    return response


@tool(permission=ToolPermission.READ_ONLY)
def get_term_dates(term: Optional[str] = None) -> dict:
    """Get the planning dates for a term or all terms: start, end, when enrolment opens and closes, the payment due date and the census date.

    Use this for the census date and payment due date of a term when planning or working out fees, including future terms. Only some dates are published by RMIT, and published_fields lists them. The rest, and all dates for 2028, are planning estimates. For what week it is, breaks, exam periods, results release and holidays use get_current_week and get_key_dates instead. Withdrawing before the census date avoids the fee.

    Args:
        term: Optional term such as 2027-S1. Leave empty for every term.

    Returns:
        found, the term calendar and a source block. If the term is unknown, found is false with a reason.
    """
    terms = load("terms.json")
    if term:
        terms = [t for t in terms if t["term"] == term]
        if not terms:
            return not_found(f"There is no calendar entry for term {term}.")
    provenances = {source(t, "terms.json")["provenance"] for t in terms}
    block = {**source(terms[0], "terms.json"), "provenance": provenances.pop() if len(provenances) == 1 else "mixed"}
    listed = [{**strip_meta(t), "published_fields": [f for f, v in t["field_provenance"].items() if v == "from_public_page"]}
              for t in terms]
    return {"found": True, "terms": listed, "source": block}
