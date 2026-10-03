"""Command line for the demo: login, logout, whoami, chat and ask.

The login is a placeholder for a web login. It resolves a username to a student number, and the chat
commands send only that number to the agent, so a conversation is tied to one student.
"""
import argparse
import getpass
import sys
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from planner import auth
from planner.client import AGENT_NAME, ChatError, connect, format_steps, ungrounded_citations
from tools.common import load


def student_name(number: str) -> str:
    try:
        return next(s["name"] for s in load("students.json") if s["student_number"] == number)
    except (FileNotFoundError, StopIteration, ValueError):
        return "unknown"


def cmd_login(args) -> int:
    username = args.user or input("Username: ")
    password = args.password if args.password is not None else getpass.getpass("Password: ")
    account = auth.authenticate(username, password)
    if account is None:
        print("Login failed: unknown username or wrong password.")
        return 1
    auth.write_session(account)
    print(f"Logged in as {username}: {student_name(account['student_number'])} ({account['student_number']}).")
    return 0


def cmd_logout(_args) -> int:
    print("Logged out." if auth.clear_session() else "No active session.")
    return 0


def cmd_whoami(_args) -> int:
    session = auth.read_session()
    if session is None:
        print("Not logged in. Run: python -m planner login")
        return 1
    hours = (session["expires_at"] - time.time()) / 3600
    print(f"{session['username']}: {student_name(session['student_number'])} ({session['student_number']}), "
          f"session ends in {hours:.1f} hours.")
    return 0


def panel(title: str, body, colour: str) -> Panel:
    return Panel(body, title=title, title_align="left", border_style=colour)


def show_user(message: str, console: Console) -> None:
    console.print(panel("👤 User", Text(message), "cyan"))


def show(reply, trace: bool, agent: str = AGENT_NAME, plain: bool = False, console: Console | None = None) -> None:
    """Print a reply in coloured panels for the query, the tool calls and the answer, or as plain text."""
    cited = ungrounded_citations(reply)
    warning = (f"Warning: the reply names {', '.join(cited)} but no such call was made this turn. "
               "Check the answer against the tool calls.") if cited else None
    took = f"Answered in {reply.seconds:.1f}s" if reply.seconds else None
    if plain:
        if trace and reply.steps:
            print("Tool calls:")
            print(format_steps(reply.steps))
        print(reply.text)
        if warning:
            print(warning)
        if took:
            print(took)
        return
    console = console or Console()
    if trace and reply.steps:
        console.print(panel("🧠 Reasoning Trace", Text(format_steps(reply.steps)), "yellow"))
    console.print(panel(f"🤖 {agent}", Markdown(reply.text), "green"))
    if warning:
        console.print(panel("⚠ Ungrounded answer", Text(warning), "red"))
    if took:
        console.print(f"[dim]{took}[/]")


def ask_with_spinner(client, message: str, thread_id, console: Console):
    with console.status("[bold green]Waiting for the agent...", spinner="dots"):
        return client.ask(message, thread_id)


def cmd_ask(args) -> int:
    console = Console()
    try:
        session = auth.require_session()
        client = connect(session["student_number"], args.agent)
        if not args.plain:
            show_user(args.message, console)
        reply = ask_with_spinner(client, args.message, args.thread_id, console)
    except (auth.SessionError, ChatError) as e:
        print(e)
        return 1
    show(reply, args.trace, args.agent, args.plain, console)
    print(f"\nThread: {reply.thread_id}", file=sys.stderr)
    return 0


def cmd_chat(args) -> int:
    try:
        session = auth.require_session()
        client = connect(session["student_number"], args.agent)
    except (auth.SessionError, ChatError) as e:
        print(e)
        return 1
    console = Console()
    console.print(f"Chatting as [bold]{student_name(session['student_number'])}[/]. Type exit to leave.")
    thread_id = None
    while True:
        try:
            message = console.input("[bold cyan]👤 You:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in ("exit", "quit", "q"):
            break
        if not message:
            continue
        if not args.plain:
            show_user(message, console)
        try:
            reply = ask_with_spinner(client, message, thread_id, console)
        except ChatError as e:
            print(e)
            continue
        thread_id = reply.thread_id
        show(reply, args.trace, args.agent, args.plain, console)
    if thread_id:
        print(f"Thread: {thread_id}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m planner", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="log in with a username and password")
    login.add_argument("--user", "-u")
    login.add_argument("--password", "-p", help="for scripted demos only; leave out to be prompted")
    login.set_defaults(run=cmd_login)
    sub.add_parser("logout", help="end the session").set_defaults(run=cmd_logout)
    sub.add_parser("whoami", help="show who is logged in").set_defaults(run=cmd_whoami)

    for name, run, help_ in [("chat", cmd_chat, "chat with the agent"), ("ask", cmd_ask, "send one message")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--agent", default=AGENT_NAME)
        p.add_argument("--trace", action="store_true", help="show the tool calls behind each reply")
        p.add_argument("--plain", action="store_true", help="plain text with no panels, for scripts and logs")
        p.set_defaults(run=run)
        if name == "ask":
            p.add_argument("message")
            p.add_argument("--thread-id", "-t", help="continue an earlier conversation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
