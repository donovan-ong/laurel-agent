import json
import stat
import time

import pytest

from planner import __main__ as cli
from planner import auth
from planner.client import ChatClient, ChatError, format_steps, message_text


@pytest.fixture(autouse=True)
def session_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNER_SESSION_FILE", str(tmp_path / "session.json"))
    return tmp_path / "session.json"


# Accounts and passwords

def test_every_demo_login_works_and_maps_to_its_student():
    for n in range(1, 9):
        account = auth.authenticate(f"demo{n}", f"demo{n}")
        assert account["student_number"] == f"S{n:07d}"


def test_wrong_password_unknown_user_and_other_students_password_are_rejected():
    assert auth.authenticate("demo1", "wrong") is None
    assert auth.authenticate("demo1", "demo2") is None
    assert auth.authenticate("nobody", "demo1") is None
    assert auth.authenticate("demo1", "") is None


def test_passwords_are_stored_as_salted_hashes_only():
    accounts = auth.load_accounts()
    assert all("password" not in a for a in accounts)
    assert all(a["password_hash"] != a["username"] for a in accounts)
    assert len({a["salt"] for a in accounts}) == len(accounts)
    same = auth.hash_password("demo1", bytes.fromhex(accounts[0]["salt"]))
    other_salt = auth.hash_password("demo1", bytes.fromhex(accounts[1]["salt"]))
    assert same == accounts[0]["password_hash"] and same != other_salt


# Session file

def test_session_holds_the_student_number_and_never_the_password(session_file):
    account = auth.authenticate("demo1", "demo1")
    auth.write_session(account, now=1000.0)
    text = session_file.read_text()
    assert json.loads(text) == {"username": "demo1", "student_number": "S0000001",
                                "logged_in_at": 1000.0, "expires_at": 1000.0 + auth.SESSION_TTL_SECONDS}
    assert "password" not in text and "hash" not in text
    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600


def test_session_expires(session_file):
    auth.write_session(auth.authenticate("demo1", "demo1"), now=1000.0)
    assert auth.read_session(now=1000.0 + 60)["student_number"] == "S0000001"
    assert auth.read_session(now=1000.0 + auth.SESSION_TTL_SECONDS) is None


def test_missing_or_corrupt_session_is_not_a_login(session_file):
    assert auth.read_session() is None
    session_file.write_text("not json")
    assert auth.read_session() is None
    session_file.write_text(json.dumps({"expires_at": time.time() + 999, "student_number": ""}))
    assert auth.read_session() is None
    with pytest.raises(auth.SessionError, match="Not logged in"):
        auth.require_session()


def test_clear_session(session_file):
    auth.write_session(auth.authenticate("demo1", "demo1"))
    assert auth.clear_session() is True and auth.clear_session() is False
    assert not session_file.exists()


# Command line

def test_login_whoami_logout(capsys, session_file):
    assert cli.main(["login", "--user", "demo4", "--password", "demo4"]) == 0
    assert "Casey Delacroix (S0000004)" in capsys.readouterr().out
    assert cli.main(["whoami"]) == 0
    assert "demo4" in capsys.readouterr().out
    assert cli.main(["logout"]) == 0
    assert not session_file.exists()
    assert cli.main(["whoami"]) == 1
    assert "Not logged in" in capsys.readouterr().out


def test_failed_login_creates_no_session(capsys, session_file):
    assert cli.main(["login", "--user", "demo1", "--password", "nope"]) == 1
    assert "Login failed" in capsys.readouterr().out
    assert not session_file.exists()


def test_login_prompts_for_the_password_when_not_given(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "demo2")
    assert cli.main(["login", "--user", "demo2"]) == 0
    assert "S0000002" in capsys.readouterr().out


def test_ask_and_chat_refuse_without_a_session_and_never_connect(monkeypatch, capsys):
    def connect_must_not_run(*args, **kwargs):
        raise AssertionError("connected without a login")
    monkeypatch.setattr(cli, "connect", connect_must_not_run)
    assert cli.main(["ask", "hello"]) == 1
    assert cli.main(["chat"]) == 1
    assert capsys.readouterr().out.count("Not logged in") == 2


def test_there_is_no_way_to_pick_the_student_from_the_command_line():
    for argv in (["ask", "hi", "--student", "S0000002"], ["chat", "--student-number", "S0000002"]):
        with pytest.raises(SystemExit):
            cli.main(argv)


class FakeClient:
    def __init__(self, student_number):
        self.student_number = student_number
        self.calls = []

    def ask(self, message, thread_id=None):
        from planner.client import Reply
        self.calls.append((message, thread_id))
        steps = [{"step_details": [{"type": "tool_calls", "tool_calls": [{"name": "get_student_profile", "args": {}}]}]}]
        return Reply("thread-1", f"reply to {message}", steps)


def test_ask_sends_the_students_number_from_the_session(monkeypatch, capsys):
    made = []
    monkeypatch.setattr(cli, "connect", lambda number, agent: made.append((number, agent)) or FakeClient(number))
    cli.main(["login", "--user", "demo3", "--password", "demo3"])
    capsys.readouterr()
    assert cli.main(["ask", "Hi", "--trace"]) == 0
    out = capsys.readouterr()
    assert made == [("S0000003", "study_planner_agent")]
    assert "reply to Hi" in out.out and "get_student_profile" in out.out
    assert "thread-1" in out.err


def test_chat_keeps_one_thread_and_stops_on_exit(monkeypatch, capsys):
    client = FakeClient("S0000001")
    monkeypatch.setattr(cli, "connect", lambda number, agent: client)
    cli.main(["login", "--user", "demo1", "--password", "demo1"])
    inputs = iter(["first", "", "second", "exit", "never asked"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    assert cli.main(["chat"]) == 0
    assert client.calls == [("first", None), ("second", "thread-1")]


# Chat client

class FakeRun:
    base_endpoint = "/runs"

    def __init__(self, status="completed"):
        self.posts, self.status = [], status

    def _post(self, endpoint, data):
        self.posts.append((endpoint, data))
        return {"run_id": "run-1", "thread_id": data.get("thread_id", "thread-1")}

    def wait_for_run_completion(self, run_id, poll_interval, max_retries):
        return {"status": self.status, "error": "boom"}


class FakeThreads:
    def __init__(self, messages):
        self.messages = messages

    def get_thread_messages(self, thread_id):
        return self.messages


ASSISTANT = {"role": "assistant", "content": [{"response_type": "text", "text": "Hello Sam"}],
             "step_history": [
                 {"step_details": [{"type": "tool_calls", "tool_calls": [{"name": "get_fees", "args": {"course_ids": ["COSC2148"]}}]}]},
                 {"step_details": [{"type": "tool_response", "name": "get_fees", "content": "x" * 900}]}]}


def test_client_sends_the_student_in_the_context_on_every_message():
    run = FakeRun()
    client = ChatClient(run, FakeThreads([{"role": "user", "content": "hi"}, ASSISTANT]), "agent-1", "S0000005")
    first = client.ask("hi")
    client.ask("again", thread_id=first.thread_id)
    for endpoint, payload in run.posts:
        assert endpoint == "/runs"
        assert payload["context"] == {"student_number": "S0000005"}
        assert payload["agent_id"] == "agent-1"
        assert "S0000005" not in payload["message"]["content"]
    assert "thread_id" not in run.posts[0][1] and run.posts[1][1]["thread_id"] == "thread-1"
    assert first.text == "Hello Sam" and len(first.steps) == 2


def test_client_reports_failed_runs_and_missing_replies():
    with pytest.raises(ChatError, match="boom"):
        ChatClient(FakeRun("failed"), FakeThreads([]), "a", "S0000001").ask("hi")
    with pytest.raises(ChatError, match="No reply"):
        ChatClient(FakeRun(), FakeThreads([{"role": "user", "content": "hi"}]), "a", "S0000001").ask("hi")
    assert ChatClient(FakeRun(), FakeThreads({"data": [ASSISTANT]}), "a", "S0000001").ask("hi").text == "Hello Sam"


def test_message_text_and_step_formatting():
    assert message_text("plain") == "plain"
    assert message_text([{"response_type": "text", "text": "a"}, {"text": "b"}]) == "a\nb"
    trace = format_steps(ASSISTANT["step_history"], max_chars=50)
    assert '-> get_fees {"course_ids": ["COSC2148"]}' in trace
    assert "<- get_fees: " + "x" * 50 + " ..." in trace
    assert format_steps([]) == "" and format_steps(None) == ""


def test_default_output_uses_panels_for_the_query_trace_and_reply(monkeypatch, capsys):
    monkeypatch.setattr(cli, "connect", lambda number, agent: FakeClient(number))
    cli.main(["login", "--user", "demo1", "--password", "demo1"])
    capsys.readouterr()
    cli.main(["ask", "Hi there", "--trace"])
    out = capsys.readouterr().out
    assert out.index("User") < out.index("Reasoning Trace") < out.index("study_planner_agent")
    assert "Hi there" in out and "get_student_profile" in out and "reply to Hi there" in out
    assert "╭" in out


def test_plain_output_has_no_panels(monkeypatch, capsys):
    monkeypatch.setattr(cli, "connect", lambda number, agent: FakeClient(number))
    cli.main(["login", "--user", "demo1", "--password", "demo1"])
    capsys.readouterr()
    cli.main(["ask", "Hi", "--trace", "--plain"])
    out = capsys.readouterr().out
    assert "╭" not in out and "Tool calls:" in out and "reply to Hi" in out


def test_a_reply_citing_a_tool_that_was_not_called_is_flagged():
    from planner.client import Reply, called_tools, ungrounded_citations
    profile_only = [{"step_details": [{"type": "tool_calls", "tool_calls": [{"name": "get_student_profile", "args": {}}]}]}]
    assert called_tools(profile_only) == {"get_student_profile"} and called_tools(None) == set()
    made_up = Reply("t", "Week 14 (source: get_current_week), exams per `get_key_dates`.", profile_only)
    assert ungrounded_citations(made_up) == ["get_current_week", "get_key_dates"]
    grounded = Reply("t", "Hello Sam, from get_student_profile.", profile_only)
    assert ungrounded_citations(grounded) == []
    assert ungrounded_citations(Reply("t", "From get_fees", [])) == ["get_fees"]
    assert ungrounded_citations(Reply("t", "No tool named here.", profile_only)) == []


def test_the_cli_shows_a_warning_for_an_ungrounded_reply(capsys):
    from planner.client import Reply
    bad = Reply("t", "Week 14, source get_current_week", [])
    cli.show(bad, trace=True, plain=True)
    assert "Warning: the reply names get_current_week" in capsys.readouterr().out
    cli.show(bad, trace=False)
    out = capsys.readouterr().out
    assert "Ungrounded answer" in out and "get_current_week" in out
    cli.show(Reply("t", "All fine"), trace=False, plain=True)
    assert "Warning" not in capsys.readouterr().out


def test_the_answer_time_is_shown_when_known(capsys):
    from planner.client import Reply
    cli.show(Reply("t", "Hi", [], 14.24), trace=False, plain=True)
    assert "Answered in 14.2s" in capsys.readouterr().out
    cli.show(Reply("t", "Hi", [], 2.5), trace=False)
    assert "Answered in 2.5s" in capsys.readouterr().out
    cli.show(Reply("t", "Hi"), trace=False, plain=True)
    assert "Answered in" not in capsys.readouterr().out


def test_the_client_times_the_whole_answer():
    run = FakeRun()
    reply = ChatClient(run, FakeThreads([ASSISTANT]), "agent-1", "S0000001").ask("hi")
    assert isinstance(reply.seconds, float) and reply.seconds >= 0


def test_agent_reply_is_rendered_as_markdown(monkeypatch, capsys):
    from planner.client import Reply
    cli.show(Reply("t", "| A | B |\n|---|---|\n| 1 | 2 |"), trace=False)
    out = capsys.readouterr().out
    assert "|---|" not in out and "1" in out and "2" in out
