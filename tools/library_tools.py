"""Library loans, due dates and renewal. No book lookup or catalogue search here - the agent points the
student to the library website's own catalogue for that (see agents/study_planner.yaml). Renewal is a
direct action like campus_services_tools, not a check-then-confirm one like enrolment or booking a room:
it is the student's own loan, does not take a seat from anyone, and the one real externality (someone
else waiting for the book) already has its own refusal reason below.
"""
from datetime import date, timedelta
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import current_student, load, not_found, source
from tools.enrolment import problem

LOAN_PERIOD_DAYS = 21
MAX_RENEWALS = 2
NOTICE = "SIMULATION: this is a demonstration. No real renewal has been made, and all the data is synthetic."


def renewal_block(loan: dict):
    if loan["on_hold_for_other"]:
        return problem("ON_HOLD_FOR_ANOTHER_STUDENT", f"{loan['title']} has a hold from another student, so it cannot be renewed.")
    if loan["renewal_count"] >= MAX_RENEWALS:
        return problem("AT_RENEWAL_LIMIT", f"{loan['title']} has already been renewed the maximum {MAX_RENEWALS} times.")
    return None


@tool(permission=ToolPermission.READ_ONLY)
def get_current_loans(context: AgentRun) -> dict:
    """Get the logged-in student's current library loans: title, author, due date, and whether each can be renewed.

    Use this for "what books do I have out", "when are they due" or "can I renew this". There is no book
    lookup or catalogue search tool - for finding or reserving a book, point the student to the library
    website's own catalogue search.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.

    Returns:
        found, the loans in due-date order, each with renewals_left and, if it cannot be renewed, why, and a source block. A student with no loans has an empty list, not an error. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    raw = load("library_loans.json")
    loans = sorted((l for l in raw if l["student_number"] == student["student_number"]), key=lambda l: l["due_date"])
    listed = [{
        "loan_id": l["loan_id"], "title": l["title"], "author": l["author"],
        "borrowed_date": l["borrowed_date"], "due_date": l["due_date"],
        "renewals_left": max(0, MAX_RENEWALS - l["renewal_count"]),
        **({"renewable": True} if renewal_block(l) is None else {"renewable": False, "reason": renewal_block(l)}),
    } for l in loans]
    return {"found": True, "loans": listed, "source": source(raw[0], "library_loans.json")}


@tool(permission=ToolPermission.READ_WRITE)
def renew_loans(context: AgentRun, loan_id: Optional[str] = None) -> dict:
    """Renew the logged-in student's library loans. This is a simulation: it does not change the real due date.

    Use this for "renew everything" or "renew this book". Leave loan_id empty to renew every loan that
    can be renewed in one call; give one to renew just that loan. This does not need the student to
    confirm first - renewing is harmless, unlike enrolling, dropping or booking a room.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        loan_id: Optional specific loan to renew, for example S0000004-L1 (from get_current_loans). Leave empty to renew all that can be.

    Returns:
        found, renewed (each with its previous and new due date), refused (each with why, such as AT_RENEWAL_LIMIT or ON_HOLD_FOR_ANOTHER_STUDENT), and a simulation notice. If nobody is logged in, found is false. If loan_id does not match one of the student's loans, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    loans = [l for l in load("library_loans.json") if l["student_number"] == student["student_number"]]
    if loan_id:
        loans = [l for l in loans if l["loan_id"] == loan_id]
        if not loans:
            return not_found(f"No loan {loan_id} was found for this login.")
    renewed, refused = [], []
    for l in loans:
        block = renewal_block(l)
        if block:
            refused.append({"loan_id": l["loan_id"], "title": l["title"], **block})
        else:
            new_due = (date.fromisoformat(l["due_date"]) + timedelta(days=LOAN_PERIOD_DAYS)).isoformat()
            renewed.append({"loan_id": l["loan_id"], "title": l["title"],
                           "previous_due_date": l["due_date"], "new_due_date": new_due})
    return {"found": True, "renewed": renewed, "refused": refused, "simulated": True, "notice": NOTICE}
