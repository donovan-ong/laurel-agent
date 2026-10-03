from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.common import load
from tools.library_tools import get_current_loans, renew_loans

# From data/library_loans.json: S0000006 has one renewable loan and one on hold for another student.
# S0000008-L3 is at the MAX_RENEWALS limit. S0000001 (admitted, not enrolled) has no loans.
ON_HOLD_STUDENT = "S0000006"
AT_LIMIT_STUDENT, AT_LIMIT_LOAN = "S0000008", "S0000008-L3"
NO_LOANS_STUDENT = "S0000001"


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def test_loans_nobody_logged_in():
    r = get_current_loans.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_a_student_not_enrolled_has_no_loans():
    r = get_current_loans.fn(context=ctx(NO_LOANS_STUDENT))
    assert r == {"found": True, "loans": [], "source": r["source"]}
    assert r["source"]["file"] == "library_loans.json"


def test_loans_are_listed_in_due_date_order_with_title_author_and_due_date():
    r = get_current_loans.fn(context=ctx(ON_HOLD_STUDENT))
    dates = [l["due_date"] for l in r["loans"]]
    assert dates == sorted(dates)
    assert all({"loan_id", "title", "author", "borrowed_date", "due_date", "renewals_left"} <= l.keys()
              for l in r["loans"])


def test_an_on_hold_loan_is_reported_as_not_renewable_with_a_reason():
    r = get_current_loans.fn(context=ctx(ON_HOLD_STUDENT))
    on_hold = next(l for l in r["loans"] if not l["renewable"])
    assert on_hold["reason"]["code"] == "ON_HOLD_FOR_ANOTHER_STUDENT"


def test_renew_nobody_logged_in():
    r = renew_loans.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_renewing_an_unknown_loan_id_is_reported_plainly():
    r = renew_loans.fn(context=ctx(ON_HOLD_STUDENT), loan_id="NOPE-L9")
    assert r["found"] is False


def test_renewing_a_specific_free_loan_extends_the_due_date_by_the_loan_period():
    before = get_current_loans.fn(context=ctx(ON_HOLD_STUDENT))
    free = next(l for l in before["loans"] if l["renewable"])
    r = renew_loans.fn(context=ctx(ON_HOLD_STUDENT), loan_id=free["loan_id"])
    assert len(r["renewed"]) == 1 and r["refused"] == []
    renewed = r["renewed"][0]
    assert renewed["previous_due_date"] == free["due_date"]
    assert renewed["new_due_date"] > renewed["previous_due_date"]


def test_renewing_an_on_hold_loan_is_refused():
    r = renew_loans.fn(context=ctx(ON_HOLD_STUDENT))
    refused_codes = {x["code"] for x in r["refused"]}
    assert "ON_HOLD_FOR_ANOTHER_STUDENT" in refused_codes


def test_renewing_a_loan_at_the_limit_is_refused():
    r = renew_loans.fn(context=ctx(AT_LIMIT_STUDENT), loan_id=AT_LIMIT_LOAN)
    assert r["renewed"] == [] and r["refused"][0]["code"] == "AT_RENEWAL_LIMIT"


def test_renew_everything_is_simulated_and_does_not_persist():
    before = load("library_loans.json")
    renew_loans.fn(context=ctx(AT_LIMIT_STUDENT))
    after = load("library_loans.json")
    assert before == after


def test_a_students_loans_never_include_another_students():
    raw = load("library_loans.json")
    r = get_current_loans.fn(context=ctx(ON_HOLD_STUDENT))
    expected = {l["loan_id"] for l in raw if l["student_number"] == ON_HOLD_STUDENT}
    assert {l["loan_id"] for l in r["loans"]} == expected and expected
