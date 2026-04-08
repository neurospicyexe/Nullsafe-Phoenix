#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Map LimbicState to Halseth writes.

After synthesis produces a LimbicState, this module:
1. Writes the full blob to POST /mind/limbic  -- REQUIRED; raises on failure
2. Upserts swarm_threads as mind threads (per companion)
3. Writes companion_notes as high-salience continuity notes

Thread and note writes are best-effort; failures are counted in the summary
but do not raise. Limbic write failure raises HalsethWriteError so the
synthesis loop can decide whether to retry or skip the pass.
"""

import logging
from typing import Optional

from services.brain.halseth_client import HalsethClient
from services.brain.synthesis.models import LimbicState

logger = logging.getLogger(__name__)

AGENT_IDS = ("cypher", "drevan", "gaia")


class HalsethWriteError(RuntimeError):
    """Raised when a required Halseth write fails."""


def _slugify(text: str) -> str:
    """Convert a thread name to a stable thread_key."""
    return text.lower().strip().replace(" ", "_").replace("/", "_")[:80]


async def write_all(client: HalsethClient, state: LimbicState) -> dict:
    """
    Write a LimbicState to Halseth via direct HTTP.

    Returns a summary dict: {"limbic": bool, "threads": int, "notes": int, "failed_threads": int, "failed_notes": int}
    Raises HalsethWriteError if the limbic state write fails -- this is the primary synthesis output
    and callers should treat failure as a signal to retry or skip the pass, not silently continue.
    """
    summary = {"limbic": False, "threads": 0, "notes": 0, "failed_threads": 0, "failed_notes": 0}

    # 1. Full LimbicState blob -- required; raise on failure so caller can handle
    result = await client.write_limbic_state(state.model_dump(mode="json"))
    if result:
        summary["limbic"] = True
        logger.info(f"[writer] LimbicState written: {result.get('state_id', '?')}")
    else:
        logger.error("[writer] LimbicState write failed -- companions will boot with stale limbic context")
        raise HalsethWriteError("LimbicState write returned falsy -- Halseth may be down")

    # 2. Swarm threads -> per-companion mind threads (best-effort)
    for thread_name in state.swarm_threads:
        thread_key = _slugify(thread_name)
        for agent_id in AGENT_IDS:
            result = await client.write_thread(
                thread_key=thread_key,
                agent_id=agent_id,
                title=thread_name,
                source="synthesis_loop",
            )
            if result:
                summary["threads"] += 1
            else:
                summary["failed_threads"] += 1
                logger.error(f"[writer] Thread write failed: {thread_key} for {agent_id}")

    # 3. Companion notes -> high-salience continuity notes (best-effort)
    for agent_id, note_text in state.companion_notes.items():
        if agent_id not in AGENT_IDS:
            continue
        if not note_text or not note_text.strip():
            continue
        result = await client.write_continuity_note(
            agent_id=agent_id,
            content=f"[synthesis] {note_text}",
            salience="high",
            source="synthesis_loop",
        )
        if result:
            summary["notes"] += 1
        else:
            summary["failed_notes"] += 1
            logger.error(f"[writer] Continuity note write failed for {agent_id}")

    logger.info(f"[writer] Write complete: {summary}")
    return summary
