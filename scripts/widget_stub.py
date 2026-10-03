"""Run the real web backend with a canned stand-in for the agent, so the widget can be built, screenshotted and
rehearsed without the Orchestrate trial (no login token, no 10-70 second waits).

    python scripts/widget_stub.py [--port 8101] [--delay 3]

Everything else is the real thing: the same routes, sessions, Bearer auth and CORS as `python -m webapp`; only
the agent is replaced. Every reply starts with "(stub)" so nobody can mistake it for the live agent.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

import webapp.server as server  # noqa: E402
from planner.client import Reply  # noqa: E402

CANNED = [
    (("loan", "library", "borrow", "renew"),
     "(stub) You have **2 books on loan**:\n\n| Title | Due | Renewable |\n| --- | --- | --- |\n"
     "| Computer Networks: Principles and Practice | 5 Sep 2026 | Yes |\n"
     "| Cloud Computing Fundamentals | 17 Sep 2026 | No (another student has a hold) |\n\n"
     "Say \"renew everything\" and I will renew what I can.\n\n"
     "Source: library loans, synthetic, snapshot 2026-09-21.", ["get_current_loans"]),
    (("room", "study space"),
     "(stub) I'll look for about an hour from 10:00. Free rooms tomorrow:\n\n"
     "- **8.5.12** (Building 8, seats 6, whiteboard and monitor)\n- **80.3.11** (Building 80, seats 6)\n"
     "- **12.2.05** (Building 12, seats 4)\n\nWant me to book one? Tell me which, or a different time.",
     ["check_room_availability"]),
    (("due", "assignment"),
     "(stub) **Assignment 2** for Data Mining and Machine Learning was due 28 September and has not been "
     "submitted.\n\nSource: Canvas, synthetic, snapshot 2026-09-21.", ["list_assignments"]),
    (("visa",),
     "(stub) I can't help with visa rules myself. The **International Student Office** "
     "(international@example.invalid) handles visa conditions and study load rules for international students. "
     "Would you like me to draft a message to them?", ["draft_enquiry"]),
]
DEFAULT = ("(stub) Hello! This is a canned reply from the widget stub, so the layout, spinner and buttons can be "
           "tried without the live agent.\n\nSource: stub, synthetic.", ["get_student_profile"])


def steps_for(tools: list[str]) -> list[dict]:
    return [{"step_details": [
        {"type": "tool_calls", "tool_calls": [{"name": t, "args": {}} for t in tools]},
        *[{"type": "tool_response", "name": t, "content": f'{{"found": true, "tool": "{t}"}}'} for t in tools],
    ]}]


class StubThreads:
    def __init__(self, thread):
        self.thread = thread

    def get_thread_messages(self, thread_id):
        return {"data": self.thread}


class StubClient:
    def __init__(self, number, delay):
        self.number, self.delay, self.thread = number, delay, []
        self.threads_client = StubThreads(self.thread)

    def ask(self, prompt, thread_id=None):
        time.sleep(self.delay)
        lowered = prompt.lower()
        text, tools = next(((t, tl) for keys, t, tl in CANNED if any(k in lowered for k in keys)), DEFAULT)
        steps = steps_for(tools)
        self.thread.append({"role": "user", "content": prompt})
        self.thread.append({"role": "assistant", "content": text, "step_history": steps})
        return Reply("stub-thread", text, steps, self.delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8101)
    parser.add_argument("--delay", type=float, default=3.0, help="seconds each reply takes")
    args = parser.parse_args()
    server.connect = lambda number, agent_name=None: StubClient(number, args.delay)
    uvicorn.run(server.create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
