import io
import json
import urllib.error
import urllib.request

import pytest

from mockapi import __main__ as run
from mockapi.events import EventBus
from mockapi.server import create_app

LOG = ("2026-09-22T08:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n"
       "2026-09-22T08:00:02Z INF |  https://bright-otter-1234.trycloudflare.com  |\n"
       "2026-09-22T08:00:03Z INF Registered tunnel connection connIndex=0 location=mel02\n")


class Process:
    def __init__(self, output, exits=None):
        self.stdout, self.exits, self.stopped = io.StringIO(output), exits, False

    def poll(self):
        return self.exits

    def terminate(self):
        self.stopped = True


def test_the_tunnel_address_is_found_in_cloudflareds_output():
    assert run.find_tunnel_url(LOG.splitlines()[1]) == "https://bright-otter-1234.trycloudflare.com"
    assert run.find_tunnel_url(LOG.splitlines()[0]) is None
    assert run.find_tunnel_url("https://example.com and https://api.trycloudflare.com/cdn-cgi") == "https://api.trycloudflare.com"
    assert run.find_tunnel_url("") is None


def test_starting_a_tunnel_returns_the_process_and_its_address():
    calls = []
    process, url = run.start_tunnel(8000, popen=lambda *a, **k: calls.append(a[0]) or Process(LOG), which=lambda name: "/usr/bin/cloudflared")
    assert url == "https://bright-otter-1234.trycloudflare.com"
    assert calls[0][:3] == ["cloudflared", "tunnel", "--no-autoupdate"] and calls[0][-1] == "http://127.0.0.1:8000"


def test_a_missing_cloudflared_says_how_to_install_it():
    with pytest.raises(RuntimeError, match="brew install cloudflared"):
        run.start_tunnel(8000, which=lambda name: None)


def test_a_tunnel_that_stops_early_is_reported():
    with pytest.raises(RuntimeError, match="stopped before"):
        run.start_tunnel(8000, popen=lambda *a, **k: Process("error\n", exits=1), which=lambda name: "x")


def test_a_tunnel_that_never_gives_an_address_is_stopped():
    process = Process("nothing useful\n")
    with pytest.raises(RuntimeError, match="in time"):
        run.start_tunnel(8000, timeout=0.5, popen=lambda *a, **k: process, which=lambda name: "x")
    assert process.stopped


def test_the_tunnel_is_not_ready_until_it_has_connected():
    without_registration = "\n".join(LOG.splitlines()[:2]) + "\n"
    process = Process(without_registration)
    with pytest.raises(RuntimeError, match="did not connect"):
        run.start_tunnel(8000, timeout=0.5, popen=lambda *a, **k: process, which=lambda name: "x")
    assert process.stopped


def test_the_first_check_waits_before_asking_for_a_new_tunnels_name():
    slept, good = [], io.BytesIO(json.dumps({"service": "mock-student-systems"}).encode())
    assert run.wait_until_reachable("https://x.trycloudflare.com", first_delay=8.0, sleep=slept.append, opener=lambda url, timeout=None: good)
    assert slept == [8.0]


def test_a_new_tunnel_is_waited_for_until_it_answers_health():
    replies = iter([urllib.error.URLError("dns"), OSError("reset"), io.BytesIO(b"<html>")])
    good = io.BytesIO(json.dumps({"service": "mock-student-systems"}).encode())

    def opener(url, timeout=None):
        assert url == "https://x.trycloudflare.com/health"
        try:
            reply = next(replies)
        except StopIteration:
            return good
        if isinstance(reply, Exception):
            raise reply
        return reply
    assert run.wait_until_reachable("https://x.trycloudflare.com/", timeout=30, sleep=lambda s: None, opener=opener) is True


def test_a_tunnel_that_never_answers_is_reported_as_unreachable():
    def opener(url, timeout=None):
        raise urllib.error.URLError("no")
    assert run.wait_until_reachable("https://x.trycloudflare.com", timeout=0.3, sleep=lambda s: None, opener=opener) is False


def test_events_are_formatted_for_the_terminal_with_the_status_colour():
    event = {"time": "08:17:55", "method": "POST", "path": "/v1/enrolments", "student": "S0000001", "status": 409, "ms": 3,
             "summary": "REFUSED ALREADY_ENROLLED [x]"}
    line = run.format_event(event)
    assert "08:17:55" in line and "POST" in line and "S0000001" in line and "[yellow]409[/]" in line
    assert "\\[x]" in line  # square brackets in a summary are not read as markup
    assert "[green]200[/]" in run.format_event({**event, "status": 200}) and "[red]500[/]" in run.format_event({**event, "status": 500})
    assert "S0000001" not in run.format_event({**event, "student": None})


def test_the_service_starts_on_a_free_port_and_answers():
    server, thread, port = run.start_server(create_app("k"), "127.0.0.1", 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            assert json.load(r)["service"] == "mock-student-systems"
    finally:
        server.should_exit = True
        thread.join(5)


def test_a_port_that_is_taken_gives_a_helpful_message():
    server, thread, port = run.start_server(create_app("k"), "127.0.0.1", 0)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            run.start_server(create_app("k"), "127.0.0.1", port)
    finally:
        server.should_exit = True
        thread.join(5)


def test_listeners_see_every_event_and_cannot_break_a_request():
    bus, seen = EventBus(), []
    bus.listeners += [seen.append, lambda e: 1 / 0]
    bus.publish({"kind": "x"})
    assert [e["kind"] for e in seen] == ["x"]


@pytest.mark.parametrize("argv,message", [
    (["--tunnel", "--public-url", "https://x.com"], "not both"),
    (["--deploy"], "needs a public address"),
    (["--today", "tomorrow"], "--today must be a date"),
])
def test_bad_options_are_refused(argv, message, capsys):
    with pytest.raises(SystemExit):
        run.main(argv)
    assert message in capsys.readouterr().err


def test_a_failed_redeploy_keeps_the_service_running_and_shows_the_command_to_retry():
    calls, log = [], []
    ok = run.redeploy("https://x.trycloudflare.com", "k1", deploy=lambda **kw: calls.append(kw) or 2, log=log.append)
    assert ok is False
    assert calls == [{"only": "enrolment", "skip_agent": True, "service": ("https://x.trycloudflare.com", "k1"), "log": log.append}]
    text = "\n".join(log)
    assert "still running" in text and "orchestrate env activate" in text
    assert "python scripts/deploy.py --only enrolment --skip-agent --api-url https://x.trycloudflare.com --api-key k1" in text


def test_a_successful_redeploy_says_nothing_more():
    log = []
    assert run.redeploy("https://x.com", "k", deploy=lambda **kw: 0, log=log.append) is True and log == []
