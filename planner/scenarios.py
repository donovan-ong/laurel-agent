"""Scripted scenarios run against the live agent through the same client as the CLI.

    python -m planner.scenarios --list
    python -m planner.scenarios --repeat 3 --workers 4
    python -m planner.scenarios --tag nfr01
    python -m planner.scenarios --skip-tag service          # the agent is deployed without the mock enrolment service
    python -m planner.scenarios --reset-service --tag drop  # the agent calls the mock service (see mockapi/)

Scenarios tagged "stateful" change what the service remembers, so with --reset-service they run one at a time
after the others, and the service is reset before and after each run.

Each scenario logs in as a demo student, asks one or more questions, and checks which tools were called,
what the reply says and that it does not cite a tool it never called. Answers vary between runs, so run
a scenario several times and look at the pass rate.
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from planner import auth
from planner.client import AGENT_NAME, ChatError, connect, ungrounded_citations

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_FILE = ROOT / "tests" / "scenarios.yaml"
REPORT_DIR = ROOT / "scenario_reports"

CHECKS = {"tools_called", "tools_called_any", "tools_not_called", "first_tool", "contains", "contains_any",
          "not_contains", "steps_not_contain", "max_seconds"}
CHARACTERS = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                            "‘": "'", "’": "'", " ": " ", " ": " ", "*": "", "`": ""})


PLATFORM_ERRORS = ("encountered an error", "temporarily unavailable", "try again in a few minutes",
                   "service unavailable", "something went wrong")


class ScenarioError(Exception):
    pass


@dataclass
class Scenario:
    id: str
    login: str
    tags: list[str]
    turns: list[dict]


@dataclass
class RunResult:
    scenario: str
    run: int
    passed: bool
    failures: list[str] = field(default_factory=list)
    seconds: float = 0.0
    tools: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    retries: int = 0


def normalise(text) -> str:
    """Lower case with unicode dashes and quotes made plain, so checks ignore typography and markdown."""
    return " ".join(str(text).translate(CHARACTERS).lower().split())


def ordered_calls(steps: list) -> list[str]:
    return [c.get("name") for s in steps or [] for d in s.get("step_details", [])
            if d.get("type") == "tool_calls" for c in d.get("tool_calls", [])]


def check_turn(checks: dict, reply) -> list[str]:
    """The ways a reply fails its checks. An empty list is a pass."""
    failures = []
    text = normalise(reply.text)
    order = ordered_calls(reply.steps)
    called = set(order)
    steps_text = normalise(json.dumps(reply.steps))
    failures += [f"did not call {t}" for t in checks.get("tools_called", []) if t not in called]
    failures += [f"called none of {group}" for group in checks.get("tools_called_any", []) if not called & set(group)]
    failures += [f"called {t}" for t in checks.get("tools_not_called", []) if t in called]
    first = checks.get("first_tool")
    if first and (not order or order[0] != first):
        failures.append(f"first tool was {order[0] if order else 'none'}, not {first}")
    failures += [f"reply lacks {s!r}" for s in checks.get("contains", []) if normalise(s) not in text]
    failures += [f"reply has none of {group}" for group in checks.get("contains_any", [])
                 if not any(normalise(s) in text for s in group)]
    failures += [f"reply contains {s!r}" for s in checks.get("not_contains", []) if normalise(s) in text]
    failures += [f"a tool result contains {s!r}" for s in checks.get("steps_not_contain", []) if normalise(s) in steps_text]
    limit = checks.get("max_seconds")
    if limit and reply.seconds > limit:
        failures.append(f"took {reply.seconds:.1f}s, over {limit}s")
    cited = ungrounded_citations(reply)
    if cited:
        failures.append(f"cites {', '.join(cited)} without calling it")
    return failures


def load_scenarios(path: Path = SCENARIO_FILE) -> list[Scenario]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    scenarios, seen = [], set()
    for raw in data["scenarios"]:
        sid = raw.get("id")
        if not sid or sid in seen:
            raise ScenarioError(f"scenario id missing or duplicated: {sid!r}")
        seen.add(sid)
        if not re.fullmatch(r"demo[1-9]\d*", str(raw.get("login", ""))):
            raise ScenarioError(f"{sid}: login must be a demo account such as demo1")
        turns = raw.get("turns") or [{"prompt": raw.get("prompt"), "checks": raw.get("checks")}]
        for i, turn in enumerate(turns, 1):
            if not turn.get("prompt") or not turn.get("checks"):
                raise ScenarioError(f"{sid} turn {i}: needs a prompt and at least one check")
            unknown = set(turn["checks"]) - CHECKS
            if unknown:
                raise ScenarioError(f"{sid} turn {i}: unknown checks {sorted(unknown)}")
        scenarios.append(Scenario(sid, raw["login"], list(raw.get("tags", [])), turns))
    return scenarios


def is_platform_error(text: str) -> bool:
    """Replies that report the platform failing, which say nothing about the agent's answers."""
    return any(p in normalise(text) for p in PLATFORM_ERRORS)


def ask_with_retry(client, prompt: str, thread_id, retries: int):
    """Ask, and ask again up to `retries` times if the run failed or the reply is a platform error."""
    used = 0
    while True:
        try:
            reply = client.ask(prompt, thread_id)
            failed = is_platform_error(reply.text)
        except ChatError:
            if used >= retries:
                raise
            reply, failed = None, True
        if not failed or used >= retries:
            return reply, used
        used += 1


def run_scenario(scenario: Scenario, run: int, make_client, retries: int = 1) -> RunResult:
    try:
        account = auth.authenticate(scenario.login, scenario.login)
        client = make_client(account["student_number"])
        thread_id, failures, tools, replies, seconds, retried = None, [], [], [], 0.0, 0
        for n, turn in enumerate(scenario.turns, 1):
            reply, used = ask_with_retry(client, turn["prompt"], thread_id, retries)
            retried += used
            thread_id = reply.thread_id
            seconds += reply.seconds
            tools += ordered_calls(reply.steps)
            replies.append(reply.text)
            prefix = f"turn {n}: " if len(scenario.turns) > 1 else ""
            if is_platform_error(reply.text):
                failures.append(prefix + "platform error: " + reply.text[:80])
            else:
                failures += [prefix + f for f in check_turn(turn["checks"], reply)]
        return RunResult(scenario.id, run, not failures, failures, round(seconds, 1), tools, replies, retried)
    except Exception as e:  # a failed run must not stop the others
        return RunResult(scenario.id, run, False, [f"error: {type(e).__name__}: {e}"])


def run_all(scenarios: list[Scenario], repeat: int, workers: int, make_client, on_result=None, retries: int = 1,
            reset=None) -> list[RunResult]:
    """Run every scenario repeat times. If reset is given (a function that clears the service's memory), the
    scenarios tagged stateful run one at a time after the rest, with a reset before and after each run."""
    stateful = [s for s in scenarios if reset and "stateful" in s.tags]
    jobs = [(s, r) for s in scenarios if s not in stateful for r in range(1, repeat + 1)]
    results = []

    def finish(result):
        results.append(result)
        if on_result:
            on_result(result)

    if reset:
        reset()
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        futures = [pool.submit(run_scenario, s, r, make_client, retries) for s, r in jobs]
        for future in as_completed(futures):
            finish(future.result())
    for s in stateful:
        for r in range(1, repeat + 1):
            reset()
            finish(run_scenario(s, r, make_client, retries))
            reset()
    order = {s.id: i for i, s in enumerate(scenarios)}
    return sorted(results, key=lambda r: (order[r.scenario], r.run))


def summarise(scenarios: list[Scenario], results: list[RunResult]) -> dict:
    by = {s.id: [r for r in results if r.scenario == s.id] for s in scenarios}
    rows = []
    for s in scenarios:
        runs = by[s.id]
        times = [r.seconds for r in runs if r.seconds]
        rows.append({"scenario": s.id, "tags": s.tags, "runs": len(runs), "passed": sum(r.passed for r in runs),
                     "median_seconds": round(statistics.median(times), 1) if times else None,
                     "max_seconds": max(times) if times else None,
                     "failures": sorted({f for r in runs for f in r.failures})})
    tagged = {}
    for tag in sorted({t for s in scenarios for t in s.tags}):
        members = [row for row in rows if tag in row["tags"]]
        tagged[tag] = {"scenarios": len(members), "all_runs_pass": sum(r["passed"] == r["runs"] for r in members),
                       "runs": sum(r["runs"] for r in members), "runs_passed": sum(r["passed"] for r in members)}
    times = [r.seconds for r in results if r.seconds]
    return {"rows": rows, "tags": tagged, "runs": len(results), "runs_passed": sum(r.passed for r in results),
            "retried_runs": sum(r.retries > 0 for r in results),
            "median_seconds": round(statistics.median(times), 1) if times else None,
            "max_seconds": max(times) if times else None}


def print_summary(summary: dict, console: Console) -> None:
    table = Table(title="Scenario results")
    for column in ("Scenario", "Pass", "Median s", "Max s", "Failures"):
        table.add_column(column, overflow="fold")
    for r in summary["rows"]:
        style = "green" if r["passed"] == r["runs"] else "red"
        table.add_row(r["scenario"], f"[{style}]{r['passed']}/{r['runs']}[/]", str(r["median_seconds"] or "-"),
                      str(r["max_seconds"] or "-"), "; ".join(r["failures"])[:160])
    console.print(table)
    for tag, t in summary["tags"].items():
        console.print(f"  {tag}: {t['all_runs_pass']}/{t['scenarios']} scenarios passed every run "
                      f"({t['runs_passed']}/{t['runs']} runs)")
    console.print(f"Overall: {summary['runs_passed']}/{summary['runs']} runs passed, median "
                  f"{summary['median_seconds']}s, slowest {summary['max_seconds']}s")
    if summary["retried_runs"]:
        console.print(f"{summary['retried_runs']} run(s) were retried after a platform error.")


def select(scenarios: list[Scenario], only: list[str], tags: list[str], skip_tags: list[str] | None = None) -> list[Scenario]:
    chosen = [s for s in scenarios if (not only or any(o in s.id for o in only)) and (not tags or set(tags) & set(s.tags))
              and not set(skip_tags or []) & set(s.tags)]
    if not chosen:
        raise ScenarioError("No scenarios match those filters.")
    return chosen


SERVICE_CONFIG = ROOT / "build" / "package" / "tools" / "service_config.json"


def service_resetter(config_path: Path | None = None, opener=urllib.request.urlopen):
    """A function that clears the mock service the deployed tools call. Its address is read from the last deploy."""
    try:
        settings = json.loads((config_path or SERVICE_CONFIG).read_text(encoding="utf-8"))
        url, key = settings["url"], settings["key"]
    except (FileNotFoundError, ValueError, KeyError):
        raise ScenarioError("No service is configured. Start `python -m mockapi --tunnel --deploy` first.") from None

    def reset() -> None:
        request = urllib.request.Request(url.rstrip("/") + "/admin/reset", method="POST", headers={"X-API-Key": key})
        try:
            with opener(request, timeout=15) as response:
                if response.status != 200:
                    raise ScenarioError(f"The service did not reset (HTTP {response.status}).")
        except urllib.error.URLError as e:
            raise ScenarioError(f"The service could not be reached to reset it: {e.reason}") from None
    return reset


def main(argv: list[str] | None = None, make_client=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m planner.scenarios", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=SCENARIO_FILE)
    parser.add_argument("--only", action="append", default=[], help="run scenarios whose id contains this text")
    parser.add_argument("--tag", action="append", default=[], help="run scenarios with this tag")
    parser.add_argument("--skip-tag", action="append", default=[], help="leave out scenarios with this tag")
    parser.add_argument("--reset-service", action="store_true",
                        help="reset the mock enrolment service before the run and around each stateful scenario")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario")
    parser.add_argument("--workers", type=int, default=3, help="scenarios run at the same time")
    parser.add_argument("--retries", type=int, default=1, help="times to ask again after a platform error")
    parser.add_argument("--agent", default=AGENT_NAME)
    parser.add_argument("--report", type=Path, help="write the results as JSON (default scenario_reports/<time>.json)")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    args = parser.parse_args(argv)
    console = Console()
    try:
        scenarios = select(load_scenarios(args.file), args.only, args.tag, args.skip_tag)
        reset = service_resetter() if args.reset_service else None
    except ScenarioError as e:
        console.print(f"[red]{e}[/]")
        return 2
    if args.list:
        for s in scenarios:
            console.print(f"{s.id:34} {s.login}  {','.join(s.tags)}")
        return 0
    make_client = make_client or (lambda number: connect(number, args.agent))
    started = time.perf_counter()

    def show(r: RunResult) -> None:
        mark = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"
        detail = "" if r.passed else "  " + "; ".join(r.failures)[:200]
        note = f" (retried {r.retries}x)" if r.retries else ""
        console.print(f"{mark} {r.seconds:5.1f}s  {r.scenario} (run {r.run}){note}{detail}")

    try:
        results = run_all(scenarios, args.repeat, args.workers, make_client, show, args.retries, reset)
    except ScenarioError as e:
        console.print(f"[red]{e}[/]")
        return 2
    summary = summarise(scenarios, results)
    print_summary(summary, console)
    console.print(f"Took {time.perf_counter() - started:.0f}s")
    if not args.no_report:
        path = args.report or REPORT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agent": args.agent, "summary": summary,
                                    "results": [r.__dict__ for r in results]}, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"Report: {path}")
    return 0 if summary["runs_passed"] == summary["runs"] else 1


if __name__ == "__main__":
    sys.exit(main())
