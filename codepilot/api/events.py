"""Event streaming bus for real-time frontend updates via Server-Sent Events (SSE)."""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List
from codepilot.models.schemas import WorkflowProgressEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Manages event queues per session for streaming progress."""

    def __init__(self):
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        if session_id not in self._queues:
            self._queues[session_id] = []
        self._queues[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        if session_id in self._queues:
            try:
                self._queues[session_id].remove(q)
                if not self._queues[session_id]:
                    del self._queues[session_id]
            except ValueError:
                pass

    def publish(self, session_id: str, event: WorkflowProgressEvent) -> None:
        if session_id in self._queues:
            for q in list(self._queues[session_id]):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass


event_bus = EventBus()
