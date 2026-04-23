from __future__ import annotations

import asyncio
import time
from typing import Dict, Tuple

DEDUP_WINDOW_S: float = 2.0
_EXPIRE_AFTER_S: float = 60.0


class MessageDedup:
    """
    In-memory dedup for Discord message_ids.

    First caller for a given message_id is the leader and runs the evaluation.
    Subsequent callers within DEDUP_WINDOW_S await the same future and receive
    the cached result. All callers get the same SwarmReply.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight: Dict[str, Tuple[asyncio.Future, float]] = {}

    async def get_or_start(self, message_id: str) -> Tuple[bool, asyncio.Future]:
        """
        Returns (is_leader, future).
        Leader: run eval then call future.set_result(reply).
        Follower: await future to get the cached reply.
        """
        async with self._lock:
            self._gc()
            if message_id in self._inflight:
                fut, _ = self._inflight[message_id]
                return False, fut
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._inflight[message_id] = (fut, time.monotonic())
            return True, fut

    def _gc(self) -> None:
        now = time.monotonic()
        stale = [k for k, (_, ts) in self._inflight.items() if now - ts > _EXPIRE_AFTER_S]
        for k in stale:
            del self._inflight[k]
