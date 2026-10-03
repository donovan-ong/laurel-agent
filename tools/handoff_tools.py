from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import load, not_found, source

NOT_SENT = "This is a draft only. It has not been sent, and this assistant cannot send messages. Copy it and send it yourself."
ASK_FIRST = ("No draft has been written yet. Tell the student which team handles this and ask whether they would "
             "like a draft message for it; only if they say yes, call draft_enquiry again with include_draft true.")


def suggest_team(text: str, teams: list[dict]) -> dict:
    """The team whose topics appear most in the text, or the school office when none does."""
    lowered = f" {text.lower()} "
    scores = [(sum(len(t.split()) for t in team["topics"] if t in lowered), i) for i, team in enumerate(teams)]
    best, index = max(scores, key=lambda s: (s[0], -s[1]))
    return teams[index] if best else next(t for t in teams if t["team_id"] == "school_office")


@tool(permission=ToolPermission.READ_ONLY)
def draft_enquiry(context: AgentRun, topic: str, details: str, suggested_team: Optional[str] = None,
                  include_draft: bool = False) -> dict:
    """Find the right university team for a question the assistant has no data for or that is outside what it can do, such as visa or study-load rules, scholarships, credit transfer, disability adjustments or a problem with an enrolment, and draft a message to them when the student wants one. The draft is never sent.

    Use this to hand off honestly instead of guessing. Put the question and everything already gathered in details, such as the courses, terms and what was tried. Leave suggested_team empty to pick the team from the topic, or pass a team id such as fees_and_payments. By default it returns only the team, its email and what it handles, so the student can be asked whether they want a draft: set include_draft to true only once the student has said yes, or has already asked for a message or to be put in touch. When a draft is returned, tell the student it has not been sent and that they must send it.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        topic: A short subject line for the message.
        details: The question and the context gathered so far, in plain sentences.
        suggested_team: Optional team id: school_office, student_connect, fees_and_payments, international_student_office, equitable_learning_services, student_support, scholarships_office or credit_and_advanced_standing.
        include_draft: True to write the draft message, only after the student has said they want one. Leave false to get just the team.

    Returns:
        found, the suggested recipient team, its email and what it handles, sent false, and a source block. With include_draft true, also the draft subject and body and a notice that nothing was sent; without it, draft_available true and a note to ask the student first. If the team id is unknown, found is false and lists the teams.
    """
    teams = load("contacts.json")
    if suggested_team:
        team = next((t for t in teams if t["team_id"] == suggested_team or t["name"].lower() == suggested_team.lower()), None)
        if team is None:
            return not_found(f"There is no team {suggested_team!r}. Teams are: {', '.join(t['team_id'] for t in teams)}.")
    else:
        team = suggest_team(f"{topic} {details}", teams)
    found = {"found": True, "team": {"team_id": team["team_id"], "name": team["name"], "email": team["email"],
                                     "use_for": team["use_for"]},
             "sent": False, "source": source(team, "contacts.json")}
    if not include_draft:
        return {**found, "draft_available": True, "next_step": ASK_FIRST}
    student = None
    number = context.request_context.get("student_number") if context and context.request_context else None
    if number:
        student = next((s for s in load("students.json") if s["student_number"] == number), None)
    who = f"{student['name']} (student number {student['student_number']}, {student['program_code']})" if student else "a student"
    signature = student["name"] if student else "A student"
    body = (f"Hello {team['name']},\n\nMy name is {who}.\n\n{details.strip()}\n\n"
           f"Could you please help or point me to the right person?\n\nThank you,\n{signature}")
    return {**found, "draft": {"to": team["email"], "subject": topic.strip(), "body": body},
            "student_included": bool(student), "notice": NOT_SENT}
