import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import common
from tools.student_tools import get_academic_record, get_fees, get_student_profile, get_term_dates

ROOT = Path(__file__).resolve().parent.parent
STUDENT_TOOLS = [get_student_profile, get_academic_record, get_fees]


def ctx(number):
    return AgentRun(request_context={"student_number": number})


def test_student_profile_is_the_logged_in_student():
    result = get_student_profile.fn(context=ctx("S0000001"))
    assert result["found"] is True
    student = result["student"]
    assert (student["student_number"], student["name"], student["fee_type"]) == ("S0000001", "Donovan Ong", "hecs_csp")
    assert "results" not in student and not {"provenance", "snapshot_date"} & student.keys()
    assert result["source"] == {"provenance": "synthetic", "snapshot_date": "2026-09-21", "file": "students.json"}


def test_each_demo_login_gets_only_their_own_profile():
    for n in range(1, 9):
        number = f"S{n:07d}"
        assert get_student_profile.fn(context=ctx(number))["student"]["student_number"] == number


def test_profile_shows_current_enrolments_with_titles_and_holds():
    student = get_student_profile.fn(context=ctx("S0000004"))["student"]
    assert [e["title"] for e in student["current_enrolments"]] == ["Data Mining", "Machine Learning", "Cloud Security", "Computer Science Honours Thesis Part A"]
    assert get_student_profile.fn(context=ctx("S0000007"))["student"]["account_hold"]["type"] == "unpaid_fees"
    assert get_student_profile.fn(context=ctx("S0000001"))["student"]["account_hold"] is None


@pytest.mark.parametrize("tool", STUDENT_TOOLS)
def test_no_login_or_unknown_student_returns_not_found(tool):
    for context in (AgentRun(), AgentRun(request_context={"student_number": ""}), None):
        assert tool.fn(context=context)["found"] is False
    unknown = tool.fn(context=ctx("S9999999"))
    assert unknown == {"found": False, "reason": "No student record was found for this login."}


@pytest.mark.parametrize("tool", STUDENT_TOOLS + [get_term_dates])
def test_no_tool_takes_a_student_number_from_the_model(tool):
    properties = set((tool.__tool_spec__.input_schema.properties or {}).keys())
    assert not properties & {"student_number", "student_id", "student", "username"}
    assert properties <= {"context", "course_ids", "term"}


def test_one_student_cannot_see_another_students_data():
    sam = json.dumps(get_academic_record.fn(context=ctx("S0000001")))
    casey = json.dumps(get_academic_record.fn(context=ctx("S0000004")))
    assert "COSC2148" not in sam and "COSC2148" in casey
    for tool in STUDENT_TOOLS:
        assert "S0000004" not in json.dumps(tool.fn(context=ctx("S0000001")))


def test_student_tools_are_read_only():
    for tool in STUDENT_TOOLS + [get_term_dates]:
        assert tool.__tool_spec__.permission.value == "read_only"


@pytest.mark.parametrize("number,marks,expected_gpa,expected_wam,passed,failed", [
    ("S0000004", [78, 85], 3.5, 81.5, 2, 0),
    ("S0000005", [55, 42], 0.5, 48.5, 1, 1),
    ("S0000006", [72, 68, 75, 81, 70, 66], 2.8, 72.0, 6, 0),
    ("S0000001", [], None, None, 0, 0),
])
def test_academic_record_matches_the_results(number, marks, expected_gpa, expected_wam, passed, failed):
    record = get_academic_record.fn(context=ctx(number))
    assert [r["mark"] for r in record["results"]] == marks
    assert (record["gpa"], record["wam"]) == (expected_gpa, expected_wam)
    assert (record["courses_passed"], record["courses_failed"]) == (passed, failed)
    assert all(isinstance(r["mark"], int) and 0 <= r["mark"] <= 100 for r in record["results"])
    assert record["credit_points_passed"] == 12 * passed if number != "S0000006" else record["credit_points_passed"] == 72


def test_failed_course_is_counted_in_gpa_and_flagged():
    record = get_academic_record.fn(context=ctx("S0000005"))
    failed = next(r for r in record["results"] if r["course_id"] == "COSC2462")
    assert (failed["mark"], failed["grade"], failed["passed"]) == (42, "NN", False)


def test_grade_bands_and_one_decimal_rounding():
    assert [common.grade_for(m) for m in (100, 80, 79, 70, 69, 60, 59, 50, 49, 0)] == \
        ["HD", "HD", "DI", "DI", "CR", "CR", "PA", "PA", "NN", "NN"]
    credit_points = {"A": 12, "B": 12, "C": 12, "D": 12}
    # (4 + 3 + 3 + 3) / 4 = 3.25 must round half up to 3.3, not to 3.2
    results = [{"course_id": c, "mark": m} for c, m in zip("ABCD", (85, 75, 75, 75))]
    assert common.gpa(results, credit_points) == 3.3
    assert common.gpa([], credit_points) is None and common.wam([], credit_points) is None
    # credit points weight the average: a 24 cp HD outweighs a 12 cp fail
    assert common.gpa([{"course_id": "A", "mark": 90}, {"course_id": "B", "mark": 10}], {"A": 24, "B": 12}) == 2.7


def test_fees_differ_by_fee_type():
    fee = {n: get_fees.fn(context=ctx(n), course_ids=["COSC2148"]) for n in ("S0000001", "S0000002", "S0000003")}
    assert [fee[n]["fee_type"] for n in fee] == ["hecs_csp", "domestic_full_fee", "international"]
    assert [fee[n]["estimate"]["total"] for n in fee] == [1800, 3600, 5400]
    assert "defer_to_hecs_help" in fee["S0000001"]["payment_options"]
    assert fee["S0000002"]["payment_options"] == fee["S0000003"]["payment_options"] == ["pay_upfront"]
    assert "visa" in fee["S0000003"]["withdrawal_rule"]
    assert set(fee["S0000001"]["all_fee_types"]) == {"hecs_csp", "domestic_full_fee", "international"}


def test_the_whole_degree_cost_is_worked_out_by_the_tool():
    expected = {"S0000001": 14400, "S0000002": 28800, "S0000003": 43200}
    for number, total in expected.items():
        d = get_fees.fn(context=ctx(number))["whole_degree"]
        rate = total / 8
        assert d["credit_points"] == 96 and d["fee"] == total
        assert d["compulsory"] == {"courses": 4, "credit_points": 60, "fee": rate * 5}
        assert d["options"] == {"courses": 3, "credit_points": 36, "fee": rate * 3}
        assert d["compulsory"]["fee"] + d["options"]["fee"] == d["fee"]


def test_fee_estimate_scales_with_credit_points_and_flags_unknown_courses():
    fees = get_fees.fn(context=ctx("S0000003"), course_ids=["COSC3155", "COSC2148", "NOPE9999"])
    assert fees["estimate"]["total"] == 10800 + 5400
    assert fees["estimate"]["unknown_course_ids"] == ["NOPE9999"]
    assert "estimate" not in get_fees.fn(context=ctx("S0000003"))


def test_fees_report_the_account_and_hold():
    account = get_fees.fn(context=ctx("S0000007"))["account"]
    assert account["balance_due"] == 3600 and account["hold"]["blocks"] == ["enrolment"]
    assert get_fees.fn(context=ctx("S0000001"))["account"]["balance_due"] == 0


def test_term_dates():
    everything = get_term_dates.fn()
    assert everything["found"] and [t["term"] for t in everything["terms"]][:2] == ["2026-S2", "2027-S1"]
    one = get_term_dates.fn(term="2027-S1")["terms"][0]
    assert one["census_date"] > one["payment_due_date"] > one["enrolment_closes"] > one["start_date"]
    assert not {"provenance", "snapshot_date", "field_provenance"} & one.keys()
    assert get_term_dates.fn(term="1999-S1") == {"found": False, "reason": "There is no calendar entry for term 1999-S1."}


def test_term_dates_say_which_dates_are_published():
    published = get_term_dates.fn(term="2026-S2")["terms"][0]
    assert published["published_fields"] == ["start_date", "enrolment_closes", "census_date", "end_date"]
    assert published["census_date"] == "2026-08-31"
    assert get_term_dates.fn(term="2026-S2")["source"]["provenance"] == "mixed"
    estimate = get_term_dates.fn(term="2028-S1")
    assert estimate["terms"][0]["published_fields"] == [] and estimate["source"]["provenance"] == "synthetic"
    assert get_term_dates.fn(term="2027-S1")["terms"][0]["published_fields"] == ["enrolment_opens"]


def test_source_reports_mixed_when_record_has_public_fields():
    record = {"provenance": "synthetic", "snapshot_date": "2026-09-21",
              "field_provenance": {"title": "from_public_page"}}
    assert common.source(record, "courses.json")["provenance"] == "mixed"
    record["field_provenance"] = {}
    assert common.source(record, "courses.json")["provenance"] == "synthetic"


def test_missing_student_file_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    assert get_student_profile.fn(context=ctx("S0000001")) == {"found": False, "reason": "Student data is not available."}


def test_tools_run_from_the_packaged_layout(tmp_path):
    """The uploaded package holds only tools/ and data/, with the package root as cwd."""
    pkg = tmp_path / "package"
    (pkg / "tools").mkdir(parents=True)
    (pkg / "data").mkdir()
    for f in (ROOT / "tools").glob("*.py"):
        shutil.copy(f, pkg / "tools" / f.name)
    for name in ("students.json", "courses.json", "fees.json", "terms.json", "programs.json"):
        shutil.copy(ROOT / "data" / name, pkg / "data" / name)
    code = ("import json; from ibm_watsonx_orchestrate.run.context import AgentRun; "
            "from tools.student_tools import get_student_profile as p, get_fees as f; "
            "c = AgentRun(request_context={'student_number': 'S0000002'}); "
            "print(json.dumps([p.fn(context=c)['student']['name'], f.fn(context=c)['fee_type']]))")
    out = subprocess.run([sys.executable, "-c", code], cwd=pkg, capture_output=True, text=True, check=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == ["Jordan Whitfield", "domestic_full_fee"]


def test_cloud_package_leaves_out_the_login_credentials():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_package.py")], check=True, capture_output=True)
    packaged = {p.name for p in (ROOT / "build" / "package" / "data").iterdir()}
    assert "accounts.json" not in packaged
    assert {"students.json", "courses.json", "fees.json", "terms.json", "key_dates.json", "timetable.json", "programs.json"} <= packaged


# The data cache

def test_load_parses_a_file_once_and_again_when_it_changes(data_copy):
    first = common.load("courses.json")
    assert common.load("courses.json") is first
    path = data_copy / "courses.json"
    path.write_text(path.read_text(encoding="utf-8").replace("Data Mining", "Data Mining X", 1), encoding="utf-8")
    changed = common.load("courses.json")
    assert changed is not first and any(c["title"] == "Data Mining X" for c in changed)


def test_load_keeps_separate_copies_for_separate_folders(data_copy):
    real = common.load("terms.json")
    (data_copy / "terms.json").write_text("[]", encoding="utf-8")
    assert common.load("terms.json") == [] and real
