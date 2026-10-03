import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import load
from tools.handoff_tools import NOT_SENT, draft_enquiry, find_support_team, suggest_team


def draft(topic, details="Some details.", team=None, number="S0000003"):
    ctx = AgentRun(request_context={"student_number": number}) if number else AgentRun()
    return draft_enquiry.fn(context=ctx, topic=topic, details=details, suggested_team=team)


def test_finding_the_team_names_it_and_writes_nothing_so_the_student_can_be_asked_first():
    r = find_support_team.fn(topic="Part-time study on my visa", details="Can I study part-time on my visa?")
    assert r["found"] and r["team"]["team_id"] == "international_student_office"
    assert r["team"]["email"] == "international@example.invalid" and r["team"]["use_for"]
    assert "draft" not in r and "ask the student" in r["next_step"]


def test_finding_and_drafting_agree_on_the_team_and_an_unknown_team_is_reported():
    found = find_support_team.fn(topic="Scholarship options", details="Are there scholarships?")
    assert draft("Scholarship options", "Are there scholarships?", team=found["team"]["team_id"])["draft"]["to"] == found["team"]["email"]
    assert find_support_team.fn(topic="x", details="y", suggested_team="the dean")["found"] is False


def test_the_team_finder_takes_no_student():
    assert "context" not in find_support_team.__tool_spec__.input_schema.properties


@pytest.mark.parametrize("topic,details,team", [
    ("Part-time study on my visa", "I am an international student.", "international_student_office"),
    ("Scholarship options", "Are there scholarships for Honours students?", "scholarships_office"),
    ("Credit transfer", "I did a unit at another university.", "credit_and_advanced_standing"),
    ("Refund", "I want a refund of my fee for a course I withdrew from.", "fees_and_payments"),
    ("Adjustments", "I have a medical condition and need an adjustment.", "equitable_learning_services"),
    ("Feeling overwhelmed", "I am stressed and need counselling.", "student_support"),
    ("Thesis supervisor", "Who could supervise my thesis?", "school_office"),
    ("Withdrawing", "I want to withdraw before the census date.", "student_connect"),
    ("Something odd", "No keywords here at all.", "school_office"),
])
def test_the_team_is_chosen_from_the_topic(topic, details, team):
    r = draft(topic, details)
    assert r["found"] and r["team"]["team_id"] == team and r["draft"]["to"] == r["team"]["email"]


def test_a_draft_is_never_sent_and_says_so():
    r = draft("Visa", "Question about my visa.")
    assert r["sent"] is False and r["notice"] == NOT_SENT and "cannot send" in r["notice"]
    assert r["source"]["file"] == "contacts.json"


def test_the_draft_names_the_student_and_carries_the_details():
    r = draft("Part-time study", "Can I study part-time on my visa in BH013P26?")
    body = r["draft"]["body"]
    assert "Noor Halvorsen" in body and "S0000003" in body and "BH013P26" in body
    assert "Can I study part-time on my visa in BH013P26?" in body and r["draft"]["subject"] == "Part-time study"
    assert r["student_included"] is True and body.startswith("Hello International Student Office")


def test_a_draft_without_a_login_is_anonymous():
    r = draft("Visa", "A visa question.", number=None)
    assert r["student_included"] is False and "S0000" not in r["draft"]["body"] and "a student" in r["draft"]["body"]


def test_only_the_logged_in_student_appears_in_the_draft():
    body = draft("Fees", "About fees.", number="S0000001")["draft"]["body"]
    assert "Donovan Ong" in body and "Noor" not in body and "S0000003" not in body


def test_a_team_can_be_named_by_id_or_by_name_and_an_unknown_one_lists_the_teams():
    assert draft("Fees", team="fees_and_payments")["team"]["team_id"] == "fees_and_payments"
    assert draft("x", team="Scholarships Office")["team"]["team_id"] == "scholarships_office"
    bad = draft("x", team="the dean")
    assert bad["found"] is False and "school_office" in bad["reason"] and "fees_and_payments" in bad["reason"]


def test_all_recipients_are_fictional_and_the_default_team_exists():
    teams = load("contacts.json")
    assert all(t["email"].endswith("@example.invalid") for t in teams)
    assert suggest_team("nothing relevant", teams)["team_id"] == "school_office"


def test_the_handoff_tool_is_read_only_and_takes_no_student():
    props = set(draft_enquiry.__tool_spec__.input_schema.properties)
    assert not props & {"student_number", "student_id"} and draft_enquiry.__tool_spec__.permission.value == "read_only"
    assert "never sent" in draft_enquiry.__tool_spec__.description
