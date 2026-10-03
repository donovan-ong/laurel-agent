"""Run the study planner web app: log in, chat and see your profile in a browser instead of the CLI.

    python -m webapp                  # http://127.0.0.1:8100
    python -m webapp --port 9000

Log in with a demo account, for example demo1 / demo1 (see README.md for the full list). Sessions live only
in this process's memory: restarting logs everyone out. The CLI (python -m planner ...) keeps working exactly
as before and is unaffected by this.
"""
import argparse
import sys
import time
import webbrowser

from rich.console import Console

from mockapi.__main__ import start_server
from webapp.server import create_app

console = Console()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--no-open", action="store_true", help="do not open the app in a browser")
    args = parser.parse_args(argv)

    app = create_app()
    try:
        server, thread, port = start_server(app, args.host, args.port)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        return 1
    url = f"http://{args.host}:{port}"
    console.print(f"Study planner web app running on [bold]{url}[/]")
    console.print("Log in with a demo account, e.g. demo1 / demo1. Ctrl-C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
