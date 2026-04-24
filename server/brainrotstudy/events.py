"""In-process pub/sub for job progress updates (used by SSE)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from .schemas import ProgressEvent


class EventBus:
    """Fan-out async queue: one publisher, many subscribers per job."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[ProgressEvent | None]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, event: ProgressEvent) -> None:
        async with self._lock:
            queues = list(self._subs.get(event.id, ()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # subscriber is too slow; drop the event rather than blocking the pipeline
                pass

    async def close(self, job_id: str) -> None:
        """Signal end-of-stream to all subscribers of a job."""
        async with self._lock:
            queues = list(self._subs.get(job_id, ()))
        for q in queues:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, job_id: str) -> AsyncIterator[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent | None] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subs[job_id].add(q)
        try:
            while True:
                evt = await q.get()
                if evt is None:
                    return
                yield evt
        finally:
            async with self._lock:
                self._subs[job_id].discard(q)
                if not self._subs[job_id]:
                    del self._subs[job_id]


bus = EventBus()
