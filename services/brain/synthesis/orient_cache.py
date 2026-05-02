#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thread-level TTL cache for canonical Halseth bot_orient blocks.

On cache miss (new thread or expired entry): fetches the canonical 16-field
bot_orient via per-companion HalsethClient, formats it into a system-prompt
injection block via format_orient_context, caches it.
On cache hit: returns the cached block immediately.
If Halseth is unreachable: returns None (caller proceeds without context).

Cache key is (thread_id, agent_id) so each companion gets its own orient
view even when sharing a thread, and switching threads invalidates.
"""

import logging
import time
from typing import Dict, Optional, Tuple

from services.brain.halseth_client import HalsethClient, format_orient_context

logger = logging.getLogger(__name__)


class OrientCache:
    """
    Thread-level TTL cache for canonical orient blocks.

    Backed by per-companion HalsethClient.bot_orient(); identical surface to
    Claude.ai's session orient and Discord-bot LibrarianClient.botOrient(),
    so Brain inference consumes the same companion mind-shape as every other
    speaking surface.

    Key: (thread_id, agent_id) -- prevents cross-agent pollution and refreshes
    on thread switch. TTL default: 300s.
    """

    def __init__(
        self,
        halseth_clients: Optional[Dict[str, HalsethClient]] = None,
        ttl_seconds: int = 300,
    ):
        self._halseth_clients = halseth_clients or {}
        self._ttl = ttl_seconds
        # {(thread_id, agent_id): (expires_at_monotonic, formatted_block)}
        self._cache: Dict[Tuple[str, str], Tuple[float, str]] = {}

    async def get(self, thread_id: str, agent_id: str) -> Optional[str]:
        """
        Return cached canonical orient block or fetch from Halseth on miss.

        Returns None if the companion has no Halseth client wired or if the
        Halseth call fails / returns no data.
        """
        now = time.monotonic()
        key = (thread_id, agent_id)
        cached = self._cache.get(key)
        if cached and now < cached[0]:
            return cached[1]

        client = self._halseth_clients.get(agent_id)
        if client is None:
            return None

        orient = await client.bot_orient()
        if orient is None:
            return None

        block = format_orient_context(orient)
        if not block:
            return None

        self._cache[key] = (now + self._ttl, block)
        return block
