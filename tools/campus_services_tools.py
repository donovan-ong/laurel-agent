"""Print balance, IT helpdesk tickets and internship/job search. Three small, unrelated services bundled
together like handoff_tools.py, none of them stateful: nothing here contends for a real resource or has a
consequence worth gating on the student's confirmation (unlike enrolment, dropping or booking a room), so
every tool acts straight away.
"""
import hashlib
from typing import List, Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import current_student, load, normalise, not_found, source

SALT = "study-planner-demo"
IT_NOTICE = "SIMULATION: this is a demonstration. No real IT ticket has been raised, and all the data is synthetic."
IT_CATEGORIES = ["account_access", "wifi_and_network", "software", "hardware", "printing", "other"]
# check_it_ticket_status has nothing real to look up (see its docstring), so the status is picked
# deterministically from the ticket number itself: the same number always gives the same answer.
IT_STATUSES = ["Open - awaiting triage", "In progress - assigned to a technician", "Resolved"]


def _digest(*parts) -> str:
    return hashlib.sha256(("|".join([SALT, *map(str, parts)])).encode()).hexdigest()


def ticket_number(student_number: str, category: str, summary: str) -> str:
    return f"IT-{int(_digest('ticket', student_number, category, summary)[:6], 16) % 1_000_000:06d}"


@tool(permission=ToolPermission.READ_ONLY)
def get_print_balance(context: AgentRun) -> dict:
    """Get the logged-in student's print credit balance.

    Use this for "how much print credit do I have" or "what's my print balance".

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.

    Returns:
        found, the balance and currency, and a source block. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    account = next((a for a in load("print_accounts.json") if a["student_number"] == student["student_number"]), None)
    if account is None:
        return not_found("No print account was found for this login.")
    return {"found": True, "balance": account["balance"], "currency": account["currency"],
            "source": source(account, "print_accounts.json")}


@tool(permission=ToolPermission.READ_ONLY)
def create_it_ticket(context: AgentRun, category: str, summary: str, details: Optional[str] = None) -> dict:
    """Raise an IT helpdesk ticket for the logged-in student. This is a simulation: no real ticket is created.

    Use this when the student has an IT problem, such as wifi, account access, software, hardware or
    printing. Unlike enrolling or booking a room, this is harmless, so raise it straight away and do not
    ask the student to confirm first. Always tell them the ticket number and the simulation notice.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        category: One of account_access, wifi_and_network, software, hardware, printing, other.
        summary: A short one-line summary of the problem.
        details: Optional further detail: what was tried, error messages, when it started.

    Returns:
        found, the ticket number, category, summary and details, a status of open, and a simulation notice. If nobody is logged in, found is false. If category is not one of the known ones, found is false and lists them.
    """
    student, error = current_student(context)
    if error:
        return error
    if category not in IT_CATEGORIES:
        return not_found(f"Unknown category {category!r}. Categories are: {', '.join(IT_CATEGORIES)}.")
    return {"found": True, "ticket_number": ticket_number(student["student_number"], category, summary),
            "category": category, "summary": summary.strip(), "details": (details or "").strip() or None,
            "status": "open", "simulated": True, "notice": IT_NOTICE}


@tool(permission=ToolPermission.READ_ONLY)
def check_it_ticket_status(context: AgentRun, ticket_number: str) -> dict:
    """Check the status of an IT helpdesk ticket. This is a simulation: there is no real ticket system behind it.

    Use this when the student asks about a ticket they were given a number for. The status is a plausible
    guess, not a real lookup: this demo never actually tracked what happened to the ticket, so the answer
    is not certain and should be given with that caveat.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        ticket_number: The ticket number, for example IT-004821.

    Returns:
        found, the ticket_number, a status, and a note that this is not a real lookup. If nobody is logged in, found is false. If the ticket number does not look like one this system issues, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    if not ticket_number.upper().startswith("IT-") or not ticket_number[3:].isdigit():
        return not_found(f"{ticket_number!r} does not look like a ticket number from this system (IT-000000).")
    index = int(_digest("status", ticket_number.upper())[:4], 16) % len(IT_STATUSES)
    return {"found": True, "ticket_number": ticket_number.upper(), "status": IT_STATUSES[index],
            "note": "This is a plausible status only, not a real lookup: nothing about this ticket was actually tracked."}


@tool(permission=ToolPermission.READ_ONLY)
def search_internships(context: AgentRun, keyword: Optional[str] = None, limit: int = 10) -> dict:
    """Search internships and jobs on the careers board for the logged-in student.

    Use this for "find me an internship", "are there any relevant jobs" or similar. Results are limited to
    listings open to the student's own program plus every listing open to all programs, in deadline order
    (soonest first). Pass keyword to also match it against the title, employer or description.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        keyword: Optional word or phrase to match, for example "data" or "casual".
        limit: The most listings to return. Default 10.

    Returns:
        found, the matching listings with their deadline and description, whether more are available, and a source block. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    listings = load("careers_listings.json")
    relevant = [l for l in listings if not l["relevant_programs"] or student["program_code"] in l["relevant_programs"]]
    if keyword:
        q = normalise(keyword)
        relevant = [l for l in relevant
                   if q in normalise(l["title"]) or q in normalise(l["employer"]) or q in normalise(l["description"])]
    relevant = sorted(relevant, key=lambda l: l["deadline"])
    listed = [{"listing_id": l["listing_id"], "title": l["title"], "employer": l["employer"], "type": l["type"],
              "location": l["location"], "deadline": l["deadline"], "description": l["description"]}
             for l in relevant[:max(limit, 1)]]
    return {"found": True, "listings": listed, "more_available": len(relevant) > max(limit, 1),
            "source": source(listings[0], "careers_listings.json")}
