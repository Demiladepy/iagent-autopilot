"""In-process asyncio pub/sub event bus."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator

# Canonical bus topics
TOPIC_EVENT = "event"
TOPIC_PROPOSAL = "proposal"
TOPIC_VERDICT = "verdict"
TOPIC_EXECUTION = "execution"
TOPIC_AUDIT = "audit"
TOPIC_AUDIT_STREAM = "audit_stream"
TOPIC_KILL = "kill"
TOPIC_SIM_INJECT = "sim_inject"

CANONICAL_TOPICS = frozenset(
    {
        TOPIC_EVENT,
        TOPIC_PROPOSAL,
        TOPIC_VERDICT,
        TOPIC_EXECUTION,
        TOPIC_AUDIT,
        TOPIC_AUDIT_STREAM,
        TOPIC_KILL,
        TOPIC_SIM_INJECT,
    }
)


class EventBus:
    """Asyncio pub/sub — one Queue per subscriber, no backpressure at our scale."""

    def __init__(self, *, queue_size: int = 0) -> None:
        # queue_size=0 → unbounded (no backpressure issues for local demo scale)
        self._queue_size = queue_size
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish *payload* to all subscribers of *topic* (and wildcard ``*``)."""
        message = {"topic": topic, **payload}
        async with self._lock:
            topic_queues = list(self._queues.get(topic, []))
            wildcard_queues = list(self._queues.get("*", []))
        for queue in topic_queues + wildcard_queues:
            await queue.put(message)

    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding messages for *topic* until cancelled."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues[topic].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                if queue in self._queues[topic]:
                    self._queues[topic].remove(queue)
