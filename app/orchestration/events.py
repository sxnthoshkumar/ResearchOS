"""
Real-Time Event Broadcaster for Server-Sent Events (SSE) and Polling Fallback.
Distributes structured execution progress events to connected research dashboards.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Pub/sub event dispatcher maintaining event queues for active research runs."""

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def broadcast(self, run_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event to all active subscribers for run_id and cache in history."""
        payload = {
            "run_id": run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self._lock:
            if run_id not in self._history:
                self._history[run_id] = []
            self._history[run_id].append(payload)
            # Bound history buffer
            if len(self._history[run_id]) > 200:
                self._history[run_id] = self._history[run_id][-200:]

            queues = self._subscribers.get(run_id, [])
            for q in queues:
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass

    async def subscribe(self, run_id: str) -> AsyncGenerator[str, None]:
        """Async generator yielding Server-Sent Events formatted data for SSE streaming."""
        queue: asyncio.Queue = asyncio.Queue()

        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = []
            self._subscribers[run_id].append(queue)

            # Send historical events immediately
            history = list(self._history.get(run_id, []))

        for event in history:
            yield f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n"

        try:
            while True:
                # Wait for new events with heartbeat timeout
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n"
                    if event.get("event_type") in ("RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"):
                        break
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep SSE connection alive
                    yield ": ping\n\n"
        finally:
            async with self._lock:
                if run_id in self._subscribers and queue in self._subscribers[run_id]:
                    self._subscribers[run_id].remove(queue)
                    if not self._subscribers[run_id]:
                        del self._subscribers[run_id]

    def get_history(self, run_id: str) -> List[Dict[str, Any]]:
        return self._history.get(run_id, [])


# Global event broadcaster
broadcaster = EventBroadcaster()
