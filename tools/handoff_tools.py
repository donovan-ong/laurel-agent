from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import load, not_found, source

NOT_SENT = "This is a draft only. It has not been sent, and this assistant cannot send messages. Copy it and send it yourself."


def suggest_team(text: str, teams: list[dict]) -> dict:
    """The team whose topics appear most in the text, or the school office when none does."""
    lowered = f" {text.lower()} "
    scores = [(sum(len(t.split()) for t in team["topics"] if t in lowered), i) for i, team in enumerate(teams)]
    best, index = max(scores, key=lambda s: (s[0], -s[1]))
    return teams[index] if best else next(t for t in teams if t["team_id"] == "school_office")


def resolve_team(topic: str, details: str, suggested_team: Optional[str]):
    """(team, error): the named team, or the one the topic and details point to."""
    teams = load("contacts.json")
    if not suggested_team:
        return suggest_team(f"{topic} {details}", teams), None
    team = next((t for t in teams if t["team_id"] == suggested_team or t["name"].lower() == suggested_team.lower()), None)
    if team is None:
        return None, not_found(f"There is no team {suggested_team!r}. Teams are: {', '.join(t['team_id'] for t in teams)}.")
    return team, None


def team_view(team: dict) -> dict:
    return {"team_id": team["team_id"], "name": team["name"], "email": team["email"], "use_for": team["use_for"]}


@tool(permission=ToolPermission.READ_ONLY)
def find_support_team(topic: str, details: str, suggested_team: Optional[str] = None) -> dict:
    """Find the university team that handles a question the assistant has no data for or that is outside what it can do, such as visa or study-load rules, scholarships, credit transfer, disability adjustments or a problem with an enrolment. It writes nothing.

    Use this first whenever you have to hand a question off, so you can name the right team and its email instead of guessing, then ask the student whether they would like a draft message to that team. Only if they say yes, call draft_enquiry. Put the question and everything already gathered in details.

    Args:
        topic: A short description of what the question is about.
        details: The question and the context gathered so far, in plain sentences.
        suggested_team: Optional team id to look up directly: school_office, student_connect, fees_and_payments, international_student_office, equitable_learning_services, student_support, scholarships_office or credit_and_advanced_standing.

    Returns:
        found, the team (name, email and what it handles), a reminder to ask before drafting, and a source block. If the team id is unknown, found is false and lists the teams.
    """
    team, error = resolve_team(topic, details, suggested_team)
    if error:
        return error
    return {"found": True, "team": team_view(team),
            "next_step": "Name this team and its email, then ask the student whether they would like a draft message "
                         "to it. Call draft_enquiry only if they say yes.",
            "source": source(team, "contacts.json")}


@tool(permission=ToolPermission.READ_ONLY)
def draft_enquiry(context: AgentRun, topic: str, details: str, suggested_team: Optional[str] = None) -> dict:
    """Draft a message the student can send to the right university team. The draft is never sent.

    Use this only once the student has said they want a draft (after find_support_team named the team), or when they asked for a message or to be put in touch in the first place, or when a drop is refused after the deadline. Put the question and everything already gathered in details, such as the courses, terms and what was tried. Pass the team id find_support_team returned as suggested_team, or leave it empty to pick the team from the topic. Tell the student the draft has not been sent and that they must send it.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        topic: A short subject line for the message.
        details: The question and the context gathered so far, in plain sentences.
        suggested_team: Optional team id: school_office, student_connect, fees_and_payments, international_student_office, equitable_learning_services, student_support, scholarships_office or credit_and_advanced_standing.

    Returns:
        found, the recipient team and email, the draft subject and body, sent false with a notice that nothing was sent, and a source block. If the team id is unknown, found is false and lists the teams.
    """
    team, error = resolve_team(topic, details, suggested_team)
    if error:
        return error
    student = None
    number = context.request_context.get("student_number") if context and context.request_context else None
    if number:
        student = next((s for s in load("students.json") if s["student_number"] == number), None)
    who = f"{student['name']} (student number {student['student_number']}, {student['program_code']})" if student else "a student"
    signature = student["name"] if student else "A student"
    body = (f"Hello {team['name']},\n\nMy name is {who}.\n\n{details.strip()}\n\n"
           f"Could you please help or point me to the right person?\n\nThank you,\n{signature}")
    return {"found": True, "team": team_view(team),
            "draft": {"to": team["email"], "subject": topic.strip(), "body": body},
            "student_included": bool(student), "sent": False, "notice": NOT_SENT,
            "source": source(team, "contacts.json")}
