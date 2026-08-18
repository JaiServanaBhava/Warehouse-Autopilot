"""SSE event hub for real-time push."""
import asyncio
import json
from typing import List


class EventHub:
    def __init__(self):
        self.queues: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.queues:
            self.queues.remove(q)

    def publish(self, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data})
        dead = []
        for q in self.queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


hub = EventHub()
