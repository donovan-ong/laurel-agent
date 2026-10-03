"""Package the data and tools, then import every tool and the agent into the active Orchestrate environment.

    python scripts/deploy.py                  # everything
    python scripts/deploy.py --only timetable # one tool file (a name contained in the file name)
    python scripts/deploy.py --skip-agent
    python scripts/deploy.py --dry-run
    python scripts/deploy.py --only enrolment --skip-agent --api-url https://abc.trycloudflare.com --api-key KEY

With --api-url and --api-key the enrolment tools call the mock enrolment service at that address (see mockapi/).
Without them the package has no service address and the tools use their own logic.

Transient platform errors (such as a 503) are retried. An expired login stops at once with the command to fix it.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "build" / "package"
AGENT_FILE = ROOT / "agents" / "study_planner.yaml"
EXPIRED = re.compile(r"token.*(missing or expired|expired)", re.I)
SUCCESS = re.compile(r"(Tool|Agent) '([^']+)' (imported|updated) successfully")


def orchestrate_command() -> str:
    local = ROOT / ".venv" / "bin" / "orchestrate"
    return str(local) if local.exists() else "orchestrate"


def run_command(command: list[str]) -> tuple[int, str]:
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def with_retries(command: list[str], runner, retries: int, pause: float, sleep=time.sleep):
    """Run a command until it reports success. Returns (ok, names, output, expired)."""
    output = ""
    for attempt in range(retries + 1):
        code, output = runner(command)
        names = [m.group(2) for m in SUCCESS.finditer(output)]
        if code == 0 and names:
            return True, names, output, False
        if EXPIRED.search(output):
            return False, [], output, True
        if attempt < retries:
            sleep(pause * (attempt + 1))
    return False, [], output, False


def tool_files(only: str | None) -> list[Path]:
    files = sorted((ROOT / "tools").glob("*_tools.py"))
    return [f for f in files if not only or only in f.name]


ADDRESS = re.compile(r"https?://[^\s/]+(/\S*)?")


def valid_service(service) -> bool:
    return bool(service) and bool(ADDRESS.fullmatch(service[0])) and bool(service[1])


def write_service_config(package: Path, url: str, key: str) -> None:
    """The address and key the enrolment tools read at run time. It goes in the package, never in the repo."""
    (package / "tools" / "service_config.json").write_text(json.dumps({"url": url.rstrip("/"), "key": key}), encoding="utf-8")


def deploy(only=None, skip_agent=False, dry_run=False, retries=3, pause=5.0, runner=run_command,
           sleep=time.sleep, log=print, service=None, package_dir=PACKAGE) -> int:
    """service is an (address, key) pair for the enrolment tools to call, or None for their own logic."""
    orchestrate = orchestrate_command()
    if service and not valid_service(service):
        log("Give --api-url as an http or https address and --api-key as the service's key.")
        return 1
    package = [sys.executable, str(ROOT / "scripts" / "build_package.py")]
    commands = [("package", package)]
    for f in tool_files(only):
        commands.append((f"tools/{f.name}", [orchestrate, "tools", "import", "-k", "python", "-f", str(package_dir / "tools" / f.name),
                                             "-p", str(package_dir), "-r", str(package_dir / "requirements.txt")]))
    if not skip_agent:
        commands.append(("agent", [orchestrate, "agents", "import", "-f", str(AGENT_FILE)]))
    if dry_run:
        for label, command in commands:
            log(f"{label}: {' '.join(command)}")
        return 0
    imported, failed = [], []
    for label, command in commands:
        if label == "package":
            code, output = runner(command)
            if code != 0:
                log(f"Packaging failed:\n{output.strip()}")
                return 1
            log("Packaged.")
            if service:
                write_service_config(Path(package_dir), *service)
                log(f"The enrolment tools will call {service[0]}")
            continue
        ok, names, output, expired = with_retries(command, runner, retries, pause, sleep)
        if expired:
            log(f"{label}: the login token is missing or expired. Run `{orchestrate} env activate <environment>` and try again.")
            return 2
        if ok:
            imported += names
            log(f"{label}: {', '.join(names)}")
        else:
            failed.append(label)
            log(f"{label}: FAILED after {retries + 1} attempts\n{output.strip()[-400:]}")
    log(f"Imported {len(imported)}: {', '.join(imported)}")
    if failed:
        log(f"Failed: {', '.join(failed)}")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="only the tool files whose name contains this text")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print the commands and run nothing")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--api-url", help="address of the mock enrolment service, for example an https tunnel address")
    parser.add_argument("--api-key", help="the service's API key")
    args = parser.parse_args(argv)
    if bool(args.api_url) != bool(args.api_key):
        parser.error("--api-url and --api-key go together")
    return deploy(args.only, args.skip_agent, args.dry_run, args.retries,
                  service=(args.api_url, args.api_key) if args.api_url else None)


if __name__ == "__main__":
    sys.exit(main())
