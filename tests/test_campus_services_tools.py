from ibm_watsonx_orchestrate.run.context import AgentRun

from tools.campus_services_tools import (check_it_ticket_status, create_it_ticket, get_print_balance,
                                         search_internships)


def ctx(number):
    return AgentRun(request_context={"student_number": number})


# Print balance

def test_print_balance_nobody_logged_in():
    r = get_print_balance.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_print_balance_reports_a_non_negative_amount():
    r = get_print_balance.fn(context=ctx("S0000004"))
    assert r["found"] is True
    assert isinstance(r["balance"], (int, float)) and r["balance"] >= 0
    assert r["currency"] == "AUD" and r["source"]["file"] == "print_accounts.json"


# IT tickets

def test_create_ticket_nobody_logged_in():
    r = create_it_ticket.fn(context=ctx(None), category="software", summary="x")
    assert r["found"] is False and "logged in" in r["reason"]


def test_create_ticket_rejects_an_unknown_category():
    r = create_it_ticket.fn(context=ctx("S0000004"), category="teleportation", summary="x")
    assert r["found"] is False and "Unknown category" in r["reason"]


def test_create_ticket_returns_a_well_formed_number_and_notice():
    r = create_it_ticket.fn(context=ctx("S0000004"), category="wifi_and_network", summary="Cannot connect to eduroam")
    assert r["found"] is True
    assert r["ticket_number"].startswith("IT-") and r["ticket_number"][3:].isdigit()
    assert r["status"] == "open" and r["simulated"] is True and "SIMULATION" in r["notice"]


def test_create_ticket_gives_different_numbers_for_different_problems():
    a = create_it_ticket.fn(context=ctx("S0000004"), category="software", summary="Excel keeps crashing")
    b = create_it_ticket.fn(context=ctx("S0000004"), category="hardware", summary="Laptop will not turn on")
    assert a["ticket_number"] != b["ticket_number"]


def test_create_ticket_gives_the_same_number_for_the_same_problem_reported_twice():
    a = create_it_ticket.fn(context=ctx("S0000004"), category="printing", summary="Printer in Building 8 is jammed")
    b = create_it_ticket.fn(context=ctx("S0000004"), category="printing", summary="Printer in Building 8 is jammed")
    assert a["ticket_number"] == b["ticket_number"]


def test_ticket_status_nobody_logged_in():
    r = check_it_ticket_status.fn(context=ctx(None), ticket_number="IT-000001")
    assert r["found"] is False and "logged in" in r["reason"]


def test_ticket_status_rejects_a_malformed_number():
    for bad in ("banana", "IT-", "IT-12A4", "004821"):
        r = check_it_ticket_status.fn(context=ctx("S0000004"), ticket_number=bad)
        assert r["found"] is False, bad


def test_ticket_status_is_stable_for_the_same_number_and_says_it_is_not_a_real_lookup():
    a = check_it_ticket_status.fn(context=ctx("S0000004"), ticket_number="IT-004821")
    b = check_it_ticket_status.fn(context=ctx("S0000004"), ticket_number="IT-004821")
    assert a["status"] == b["status"]
    assert "not a real lookup" in a["note"]


# Careers search

def test_search_nobody_logged_in():
    r = search_internships.fn(context=ctx(None))
    assert r["found"] is False and "logged in" in r["reason"]


def test_search_includes_open_to_all_listings_for_every_program():
    r = search_internships.fn(context=ctx("S0000004"), limit=100)  # BH013P26
    ids = {l["listing_id"] for l in r["listings"]}
    assert "L0004" in ids  # IT Support Officer (Casual), relevant_programs is empty


def test_search_excludes_listings_restricted_to_another_program():
    # S0000004 (Casey Delacroix) is on BH013P26; "IT Helpdesk Graduate" (L0012) is restricted to BP162P23.
    r = search_internships.fn(context=ctx("S0000004"), limit=100)
    assert "L0012" not in {l["listing_id"] for l in r["listings"]}


def test_search_keyword_matches_title_employer_or_description():
    r = search_internships.fn(context=ctx("S0000004"), keyword="database")
    assert r["listings"] and all("database" in (l["title"] + l["description"]).lower() for l in r["listings"])


def test_search_results_are_sorted_by_deadline_and_respect_the_limit():
    r = search_internships.fn(context=ctx("S0000004"), limit=3)
    deadlines = [l["deadline"] for l in r["listings"]]
    assert deadlines == sorted(deadlines) and len(r["listings"]) <= 3
