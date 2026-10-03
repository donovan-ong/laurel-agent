import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deploy", ROOT / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
sys.modules["deploy"] = deploy
spec.loader.exec_module(deploy)


def ok(kind, *names):
    return 0, "".join(f"[INFO] - {kind} '{n}' imported successfully\n" for n in names)


class Runner:
    def __init__(self, script=None):
        self.commands, self.script = [], script or (lambda command, n: None)

    def __call__(self, command):
        self.commands.append(command)
        scripted = self.script(command, len(self.commands))
        if scripted:
            return scripted
        if command[1].endswith("build_package.py"):
            return 0, "Packaged"
        if "agents" in command:
            return ok("Agent", "study_planner_agent")
        return ok("Tool", Path(command[command.index("-f") + 1]).stem)


def run(runner, **kwargs):
    logs = []
    code = deploy.deploy(runner=runner, sleep=lambda s: None, log=logs.append, **kwargs)
    return code, "\n".join(logs)


def test_it_packages_then_imports_every_tool_file_then_the_agent():
    runner = Runner()
    code, log = run(runner)
    assert code == 0
    kinds = ["package" if "build_package.py" in c[1] else "agent" if "agents" in c else "tool" for c in runner.commands]
    assert kinds[0] == "package" and kinds[-1] == "agent" and kinds.count("tool") == len(list((ROOT / "tools").glob("*_tools.py")))
    files = [Path(c[c.index("-f") + 1]).name for c in runner.commands if "tools" in c and "import" in c]
    assert files == sorted(files) and "enrolment_tools.py" in files and "student_tools.py" in files
    assert "Imported" in log and "study_planner_agent" in log


def test_tools_are_imported_from_the_clean_package_not_the_repo():
    runner = Runner()
    run(runner)
    tool_commands = [c for c in runner.commands if "tools" in c and "import" in c]
    assert all("build/package" in c[c.index("-f") + 1] and c[c.index("-p") + 1].endswith("build/package") for c in tool_commands)


def test_a_transient_failure_is_retried_and_then_succeeds():
    def script(command, n):
        if "student_tools.py" in " ".join(command) and not hasattr(script, "failed"):
            script.failed = 1
            return 1, "requests.exceptions.HTTPError: 503 Server Error: Service Unavailable"
    runner = Runner(script)
    code, log = run(runner)
    assert code == 0 and sum("student_tools.py" in " ".join(c) for c in runner.commands) == 2


def test_a_persistent_failure_is_reported_and_the_rest_still_run():
    def script(command, n):
        if "handoff_tools.py" in " ".join(command):
            return 1, "503 Service Unavailable"
    runner = Runner(script)
    code, log = run(runner, retries=2)
    assert code == 1 and "handoff_tools.py: FAILED after 3 attempts" in log and "Failed: tools/handoff_tools.py" in log
    assert sum("handoff_tools.py" in " ".join(c) for c in runner.commands) == 3
    assert any("agents" in c for c in runner.commands)


def test_an_expired_login_stops_at_once_with_the_fix():
    def script(command, n):
        if "import" in command:
            return 1, "[ERROR] - The token found for environment 'trial' is missing or expired. Use `orchestrate env activate trial`"
    runner = Runner(script)
    code, log = run(runner)
    assert code == 2 and "env activate" in log and "expired" in log
    assert sum("import" in c for c in runner.commands) == 1  # no retries, no further imports


def test_a_command_that_succeeds_without_saying_so_is_not_counted():
    runner = Runner(lambda command, n: (0, "nothing useful") if "import" in command else None)
    code, log = run(runner, retries=1)
    assert code == 1 and "FAILED after 2 attempts" in log


def test_only_and_skip_agent():
    runner = Runner()
    code, _ = run(runner, only="timetable", skip_agent=True)
    imports = [c for c in runner.commands if "import" in c]
    assert code == 0 and len(imports) == 1 and "timetable_tools.py" in " ".join(imports[0])
    assert not any("agents" in c for c in runner.commands)


def test_a_dry_run_prints_the_commands_and_runs_nothing():
    runner, logs = Runner(), []
    assert deploy.deploy(dry_run=True, runner=runner, log=logs.append) == 0
    assert runner.commands == [] and any("agents import" in line for line in logs) and any("package:" in line for line in logs)


def test_a_packaging_failure_stops_before_importing():
    runner = Runner(lambda command, n: (1, "Data failed validation") if "build_package.py" in command[1] else None)
    code, log = run(runner)
    assert code == 1 and "Packaging failed" in log and len(runner.commands) == 1


def test_the_orchestrate_command_prefers_the_local_venv():
    assert deploy.orchestrate_command().endswith("orchestrate")


# The enrolment service address

def test_the_service_address_and_key_are_written_into_the_package_after_it_is_built(tmp_path):
    (tmp_path / "tools").mkdir()
    runner = Runner()
    code, log = run(runner, service=("https://abc-def.trycloudflare.com/", "sekrit"), package_dir=tmp_path)
    assert code == 0
    written = json.loads((tmp_path / "tools" / "service_config.json").read_text())
    assert written == {"url": "https://abc-def.trycloudflare.com", "key": "sekrit"}
    assert "https://abc-def.trycloudflare.com" in log and "sekrit" not in log
    assert all(str(tmp_path) in c[c.index("-p") + 1] for c in runner.commands if "import" in c and "tools" in c)


def test_without_a_service_no_address_is_written(tmp_path):
    (tmp_path / "tools").mkdir()
    code, _ = run(Runner(), package_dir=tmp_path)
    assert code == 0 and not (tmp_path / "tools" / "service_config.json").exists()


@pytest.mark.parametrize("service", [("abc.trycloudflare.com", "k"), ("ftp://x.com", "k"), ("https://x.com", ""), ("https://", "k"),
                                     ("https://x .com", "k"), ("", "k")])
def test_a_bad_service_address_or_key_stops_before_anything_runs(tmp_path, service):
    runner = Runner()
    code, log = run(runner, service=service, package_dir=tmp_path)
    assert code == 1 and runner.commands == [] and "--api-url" in log


def test_the_service_options_go_together():
    with pytest.raises(SystemExit):
        deploy.main(["--api-url", "https://x.com", "--dry-run"])
    with pytest.raises(SystemExit):
        deploy.main(["--api-key", "k", "--dry-run"])


@pytest.mark.parametrize("path", sorted((ROOT / "tools").glob("*_tools.py")), ids=lambda p: p.name)
def test_each_tool_file_exposes_only_the_tools_it_defines(path):
    # `orchestrate tools import` registers every tool in a file's namespace, so a tool imported by name from
    # another file would be re-registered from this one.
    from ibm_watsonx_orchestrate.agent_builder.tools.python_tool import PythonTool
    module = importlib.import_module(f"tools.{path.stem}")
    for name, value in vars(module).items():
        if isinstance(value, PythonTool):
            assert value.fn.__module__ == module.__name__, f"{name} is imported into {path.name}; import its module instead"
