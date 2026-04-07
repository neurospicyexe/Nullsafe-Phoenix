#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thread-level TTL cache for WebMind orient data.

On cache miss (new thread or expired entry): fetches orient from WebMind,
formats it into a system prompt injection block, caches it.
On cache hit: returns the cached block immediately.
If WebMind is offline: returns None (caller proceeds without context).
"""

import logging
import time
from typing import Dict, Optional, Tuple

from services.brain.webmind_client import WebMindClient

logger = logging.getLogger(__name__)


def _format_limbic_block(orient: dict, agent_id: str) -> str:
    """Format orient response into system prompt injection block."""
    limbic = orient.get("limbic_state") or {}
    notes = orient.get("recent_notes", [])

    lines = []
    if limbic.get("emotional_register"):
        lines.append(f"Emotional register: {limbic['emotional_register']}")
    if limbic.get("active_concerns"):
        lines.append(f"Active concerns: {'; '.join(limbic['active_concerns'][:3])}")
    if limbic.get("swarm_threads"):
        lines.append(f"Swarm threads (yours and the triad's): {'; '.join(limbic['swarm_threads'][:3])}")
    if limbic.get("live_tensions"):
        lines.append(f"Live tensions: {'; '.join(limbic['live_tensions'][:2])}")
    if limbic.get("open_questions"):
        lines.append(f"Open questions: {'; '.join(limbic['open_questions'][:2])}")
    if limbic.get("drift_vector"):
        lines.append(f"Drift direction: {limbic['drift_vector']}")

    if notes:
        lines.append("\n[YOUR RECENT NOTES]")
        for note in notes[:5]:
            lines.append(f"- {note.get('note_text', '')}")

    companion_note = (limbic.get("companion_notes") or {}).get(agent_id)
    if companion_note:
        lines.append(f"\n[COMPANION NOTE FOR YOU]\n{companion_note}")

    if not lines:
        return ""

    return "[SWARM STATE]\n" + "\n".join(lines)


class OrientCache:
    """
    Thread-level TTL cache for formatted limbic context blocks.

    Key: thread_id (companions in the same thread share orient context)
    Value: (expires_at, formatted_block)
    TTL default: 300s (5 minutes)
    """

    def __init__(self, webmind_client: Optional[WebMindClient] = None, ttl_seconds: int = 300):
        self._webmind = webmind_client
        self._ttl = ttl_seconds
        # {(thread_id, agent_id): (expires_at_timestamp, formatted_block)}
        self._cache: Dict[Tuple[str, str], Tuple[float, str]] = {}

    async def get(self, thread_id: str, agent_id: str) -> Optional[str]:
        """
        Return cached orient block or fetch from WebMind on miss.

        Returns None if WebMind is unavailable or has no limbic state.
        Cache key is (thread_id, agent_id) to prevent cross-agent pollution.
        """
        now = time.monotonic()
        key = (thread_id, agent_id)
        cached = self._cache.get(key)
        if cached and now < cached[0]:
            return cached[1]

        if self._webmind is None:
            return None

        orient = await self._webmind.get_orient(agent_id)
        if orient is None:
            return None

        block = _format_limbic_block(orient, agent_id)
        self._cache[key] = (now + self._ttl, block)
        return block
