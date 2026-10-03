"""The request log: the last events kept in memory, and live subscribers for the dashboard's stream."""
import asyncio
import itertools
import json
import threading
from collections import deque


class EventBus:
    def __init__(self, keep: int = 500):
        self.lock = threading.Lock()
        self.events: deque = deque(maxlen=keep)
        self.subscribers: list[tuple] = []
        self.listeners: list = []
        self.ids = itertools.count(1)

    def publish(self, event: dict) -> dict:
        with self.lock:
            event = {**event, "id": next(self.ids)}
            self.events.append(event)
            subscribers = list(self.subscribers)
        for queue, loop in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        for listen in self.listeners:
            try:
                listen(event)
            except Exception:  # a broken listener must not fail the request
                pass
        return event

    def last_id(self) -> int:
        with self.lock:
            return self.events[-1]["id"] if self.events else 0

    def since(self, last_id: int = 0) -> list[dict]:
        with self.lock:
            return [e for e in self.events if e["id"] > last_id]

    def clear(self) -> None:
        with self.lock:
            self.events.clear()

    def subscribe(self):
        queue, loop = asyncio.Queue(), asyncio.get_running_loop()
        with self.lock:
            self.subscribers.append((queue, loop))
        return queue, loop

    def unsubscribe(self, queue, loop) -> None:
        with self.lock:
            self.subscribers = [s for s in self.subscribers if s[0] is not queue]


def frame(event: dict) -> str:
    """One event as a server-sent event. The id lets a reconnecting browser carry on where it stopped."""
    return f"id: {event['id']}\nevent: request\ndata: {json.dumps(event)}\n\n"


async def stream(bus: EventBus, after: int = 0, heartbeat: float = 15.0):
    """Recent events after an id, then new ones as they happen, with a comment now and then to keep the connection open."""
    queue, loop = bus.subscribe()
    try:
        sent = after
        for event in bus.since(after):
            sent = event["id"]
            yield frame(event)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), heartbeat)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event["id"] > sent:
                sent = event["id"]
                yield frame(event)
    finally:
        bus.unsubscribe(queue, loop)
