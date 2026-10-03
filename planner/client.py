"""Chat client that sends every message with the logged-in student in the run context."""
import json
import re
import time
from dataclasses import dataclass, field

AGENT_NAME = "study_planner_agent"
TRACE_CHARS = 600


class ChatError(Exception):
    pass


@dataclass
class Reply:
    thread_id: str
    text: str
    steps: list = field(default_factory=list)
    seconds: float = 0.0


def message_text(content) -> str:
    """The text of an assistant message, which may be a string or a list of typed parts."""
    if isinstance(content, list):
        parts = [i["text"] for i in content if isinstance(i, dict) and i.get("text")]
        return "\n".join(parts) or str(content)
    return str(content)


def format_steps(steps: list, max_chars: int = TRACE_CHARS) -> str:
    """Tool calls and their results from a reply's step history (US-18)."""
    lines = []
    for step in steps or []:
        for detail in step.get("step_details", []):
            if detail.get("type") == "tool_calls":
                for call in detail.get("tool_calls", []):
                    args = call.get("args") or {}
                    lines.append(f"  -> {call.get('name')}" + (f" {json.dumps(args)}" if args else ""))
            elif detail.get("type") == "tool_response":
                content = str(detail.get("content", ""))
                if len(content) > max_chars:
                    content = content[:max_chars] + " ..."
                lines.append(f"  <- {detail.get('name', 'tool')}: {content}")
    return "\n".join(lines)


TOOL_NAME = re.compile(r"\bget_[a-z_]+\b")


def called_tools(steps: list) -> set[str]:
    return {c.get("name") for s in steps or [] for d in s.get("step_details", [])
            if d.get("type") == "tool_calls" for c in d.get("tool_calls", [])}


def ungrounded_citations(reply: "Reply") -> list[str]:
    """Tools the reply names that were not called in this turn. A reply citing one may be made up."""
    return sorted(set(TOOL_NAME.findall(reply.text)) - called_tools(reply.steps))


class ChatClient:
    """One student's conversation. The student number goes in the run context, never in the message."""

    def __init__(self, run_client, threads_client, agent_id: str, student_number: str,
                 poll_interval: int = 2, max_retries: int = 90):
        self.run_client = run_client
        self.threads_client = threads_client
        self.agent_id = agent_id
        self.student_number = student_number
        self.poll_interval = poll_interval
        self.max_retries = max_retries

    def ask(self, message: str, thread_id: str | None = None) -> Reply:
        started = time.perf_counter()
        payload = {
            "message": {"role": "user", "content": message},
            "agent_id": self.agent_id,
            "context": {"student_number": self.student_number},
        }
        if thread_id:
            payload["thread_id"] = thread_id
        run = self.run_client._post(self.run_client.base_endpoint, data=payload)
        status = self.run_client.wait_for_run_completion(
            run["run_id"], poll_interval=self.poll_interval, max_retries=self.max_retries)
        if status.get("status") == "failed":
            raise ChatError(f"The run failed: {status.get('error', 'unknown error')}")
        messages = self.threads_client.get_thread_messages(run["thread_id"])
        if isinstance(messages, dict):
            messages = messages.get("data", [])
        final = next((m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"), None)
        if final is None:
            raise ChatError("No reply was received.")
        return Reply(run["thread_id"], message_text(final.get("content", "")), final.get("step_history") or [],
                     round(time.perf_counter() - started, 1))


def connect(student_number: str, agent_name: str = AGENT_NAME) -> ChatClient:
    """Build a client from the active Orchestrate environment (`orchestrate env activate`)."""
    from ibm_watsonx_orchestrate.cli.commands.agents.agents_helper import get_agent_id_by_name
    from ibm_watsonx_orchestrate.client.chat.run_client import RunClient
    from ibm_watsonx_orchestrate.client.threads.threads_client import ThreadsClient
    from ibm_watsonx_orchestrate.client.utils import instantiate_client

    agent_id = get_agent_id_by_name(agent_name)
    if not agent_id:
        raise ChatError(f"Agent {agent_name} was not found in the active environment.")
    return ChatClient(instantiate_client(RunClient), instantiate_client(ThreadsClient), agent_id, student_number)
