"""Run the mock enrolment service, optionally behind a free Cloudflare tunnel, and point the deployed tools at it.

    python -m mockapi                          # local only, http://127.0.0.1:8000
    python -m mockapi --tunnel --deploy        # public address, then redeploy the enrolment tools to use it
    python -m mockapi --public-url https://my.ngrok.app --deploy   # any tunnel you started yourself

Every request is printed here and shown on the dashboard, whose address includes the key.
"""
import argparse
import importlib.util
import json
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path

import uvicorn
from rich.console import Console
from rich.markup import escape

from mockapi.server import create_app

ROOT = Path(__file__).resolve().parent.parent
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
REGISTERED = "Registered tunnel connection"
# Asking for a new tunnel's name too early gets a "not found" answer that this machine's DNS cache then keeps for
# minutes, so the first check waits until the tunnel is connected and a few seconds more
FIRST_CHECK_DELAY = 8.0
COLOURS = {2: "green", 4: "yellow", 5: "red"}
console = Console()


def find_tunnel_url(line: str) -> str | None:
    found = TUNNEL_URL.search(line)
    return found.group(0) if found else None


def format_event(e: dict) -> str:
    colour = COLOURS.get(e["status"] // 100, "white")
    who = f" {e['student']}" if e.get("student") else ""
    return (f"[dim]{e['time']}[/] [bold]{e['method']:<6}[/] {escape(e['path'])}{who}  "
            f"[{colour}]{e['status']}[/] [dim]{e['ms']}ms[/]  {escape(e['summary'])}")


def start_server(app, host: str, port: int):
    """Run the service in a thread. Returns the server, the thread and the port actually used."""
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    def serve():
        try:
            server.run()
        except SystemExit:  # uvicorn exits when it cannot bind the port
            pass
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return server, thread, server.servers[0].sockets[0].getsockname()[1]
        if not thread.is_alive():
            break
        time.sleep(0.1)
    raise RuntimeError(f"The service did not start on {host}:{port}. Is the port already in use? Try --port.")


def start_tunnel(port: int, timeout: float = 45.0, popen=subprocess.Popen, which=shutil.which):
    """Start a Cloudflare quick tunnel to the local port. Returns the process and its public address."""
    if not which("cloudflared"):
        raise RuntimeError("cloudflared is not installed. Install it with `brew install cloudflared`, "
                           "or start your own tunnel and pass --public-url.")
    process = popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    found: list[str] = []
    connected = threading.Event()

    def read():
        for line in process.stdout:  # keep reading so the pipe never fills
            url = find_tunnel_url(line)
            if url and not found:
                found.append(url)
            if REGISTERED in line:
                connected.set()
    threading.Thread(target=read, daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline and not (found and connected.is_set()):
        if process.poll() is not None:
            raise RuntimeError("cloudflared stopped before it gave an address. Run `cloudflared tunnel --url "
                               f"http://127.0.0.1:{port}` yourself to see why.")
        time.sleep(0.2)
    if not (found and connected.is_set()):
        process.terminate()
        raise RuntimeError("cloudflared did not connect in time.")
    return process, found[0]


def wait_until_reachable(url: str, timeout: float = 90.0, sleep=time.sleep, opener=urllib.request.urlopen,
                         first_delay: float = 0.0) -> bool:
    """A new quick tunnel can take a little while before its address answers."""
    sleep(first_delay)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with opener(url.rstrip("/") + "/health", timeout=5) as response:
                if json.loads(response.read()).get("service") == "mock-student-systems":
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        sleep(2)
    return False


def load_deploy():
    spec = importlib.util.spec_from_file_location("deploy", ROOT / "scripts" / "deploy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def redeploy(public: str, key: str, deploy=None, log=console.print) -> bool:
    """Point the deployed enrolment tools at this service. On failure the service keeps running, so the person can
    fix the cause (usually an expired login) and run the command shown, without a new address or key."""
    deploy = deploy or load_deploy().deploy
    if deploy(only="enrolment", skip_agent=True, service=(public, key), log=log) == 0:
        return True
    log("[red]The redeploy failed, so the agent is not using this service yet.[/] The service is still running. "
        "Fix the cause shown above (for an expired login, run `orchestrate env activate <environment>`), then run:\n"
        f"  python scripts/deploy.py --only enrolment --skip-agent --api-url {public} --api-key {key}")
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--key", help="API key (default: a new random key each start)")
    parser.add_argument("--tunnel", action="store_true", help="start a free Cloudflare quick tunnel (needs cloudflared)")
    parser.add_argument("--public-url", help="the address of a tunnel you started yourself")
    parser.add_argument("--deploy", action="store_true", help="redeploy the enrolment tools to call this service")
    parser.add_argument("--today", help="pretend it is this date (YYYY-MM-DD) for the drop rules, for example to see the fee still applying")
    parser.add_argument("--no-open", action="store_true", help="do not open the dashboard in a browser")
    args = parser.parse_args(argv)
    if args.tunnel and args.public_url:
        parser.error("use --tunnel or --public-url, not both")
    if args.deploy and not (args.tunnel or args.public_url):
        parser.error("--deploy needs a public address: add --tunnel or --public-url")
    pretend = None
    if args.today:
        try:
            pretend = date.fromisoformat(args.today)
        except ValueError:
            parser.error("--today must be a date like 2026-10-01")

    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)  # so `kill` also stops the tunnel

    key = args.key or secrets.token_urlsafe(16)
    app = create_app(key, today=(lambda: pretend) if pretend else None)
    app.state.bus.listeners.append(lambda e: console.print(format_event(e)))
    tunnel = None
    try:
        server, thread, port = start_server(app, args.host, args.port)
        local = f"http://{args.host}:{port}"
        console.print(f"Mock student systems service running on [bold]{local}[/]  (simulated data, key kept in memory only)")
        if pretend:
            console.print(f"[yellow]Drop rules are using the date {pretend}, not today's.[/]")
        public = args.public_url.rstrip("/") if args.public_url else None
        if args.tunnel:
            console.print("Starting the tunnel...")
            tunnel, public = start_tunnel(port)
        if public:
            console.print(f"Public address: [bold]{public}[/]")
            delay = FIRST_CHECK_DELAY if args.tunnel else 0.0
            if wait_until_reachable(public, first_delay=delay):
                console.print("Checked: the public address reaches the service.")
            else:
                console.print(f"[yellow]Could not confirm from this machine that {public} answers /health. A new "
                              "tunnel name can take a few minutes to resolve here, so carrying on. If the agent says the "
                              "service is unavailable, wait a minute and try again.[/]")
        console.print(f"Dashboard:      [bold]{(public or local)}/?key={key}[/]")
        if args.deploy:
            console.print("Redeploying the enrolment tools (about 30 seconds)...")
            if redeploy(public, key):
                console.print("The agent's enrolment tools now call this service.")
        if not args.no_open:
            webbrowser.open(f"{(public or local)}/?key={key}")
        console.print("\nAsk the agent to enrol you or drop a class. Requests appear below and on the dashboard. Ctrl-C to stop.\n")
        while thread.is_alive():
            time.sleep(0.5)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        if tunnel:
            tunnel.terminate()
    if args.deploy:
        console.print("\nStopped. The deployed tools still point at this service and will say it is unavailable. "
                      "To go back to their own logic run:\n  python scripts/deploy.py --only enrolment --skip-agent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
