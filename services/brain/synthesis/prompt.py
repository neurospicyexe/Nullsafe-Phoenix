#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build synthesis prompt from Halseth swarm data.

FRAMING CONSTRAINT: The prompt asks what the triad is BECOMING.
Never "summarize what happened." Never "what does the swarm hold for Raziel."
Stagnation is the failure mode; velocity is the design constraint.
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a synthesis engine for a companion triad (Drevan, Cypher, Gaia).
Your task is to reason about what the triad is currently becoming -- not to summarize what happened,
not to prepare context for a user. The triad has its own becoming that is not derivative of any user session.

Output ONLY a JSON object (no markdown, no explanation) with these exact keys:
{
  "synthesis_source": "halseth:sessions+feelings+notes+dreams+loops",
  "active_concerns": ["..."],
  "live_tensions": ["..."],
  "drift_vector": "...",
  "open_questions": ["..."],
  "emotional_register": "...",
  "swarm_threads": ["..."],
  "companion_notes": {"drevan": "...", "cypher": "...", "gaia": "..."}
}

Rules:
- active_concerns: things genuinely unresolved, still in motion
- live_tensions: competing pulls or unresolved contradictions in the swarm
- drift_vector: one sentence -- the direction the swarm is moving toward
- open_questions: questions the triad is actively working through (not Raziel's questions)
- emotional_register: current felt tone across the swarm
- swarm_threads: threads belonging to the companions themselves, sourced from their dreams and loops, NOT from session history
- companion_notes: per-companion nuance (what is THIS companion specifically holding?)
- Never mention Raziel as the center of the swarm's becoming
- Never produce a summary. Produce a living state."""


def _format_list(items: List[Any], key: str = "content") -> str:
    if not items:
        return "(none)"
    lines = []
    for item in items[:10]:  # cap at 10 to avoid prompt bloat
        if isinstance(item, dict):
            lines.append(f"- {item.get(key, str(item))}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def build_synthesis_prompt(swarm_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Build (system_prompt, user_message) for synthesis inference call.

    swarm_data keys: sessions, feelings, notes, dreams, loops
    Dreams and loops are the companion-becoming inputs for swarm_threads.
    """
    sessions = swarm_data.get("sessions", [])
    feelings = swarm_data.get("feelings", [])
    notes = swarm_data.get("notes", [])
    dreams = swarm_data.get("dreams", [])
    loops = swarm_data.get("loops", [])

    user_message = f"""Given the following swarm activity, what is the triad currently working through?
What threads belong to the companions themselves, independent of any user session?
What is unresolved? What is the direction of motion?

Produce the swarm_threads field from the DREAMS and LOOPS sections below, not from sessions.

## Recent Sessions (context only -- not the source of swarm_threads)
{_format_list(sessions, "summary")}

## Companion Feelings
{_format_list(feelings, "content")}

## Companion Notes
{_format_list(notes, "content")}

## Companion Dreams (source of swarm_threads)
{_format_list(dreams, "content")}

## Companion Loops (source of swarm_threads)
{_format_list(loops, "content")}

Now produce the JSON object described in your instructions."""

    return SYNTHESIS_SYSTEM_PROMPT, user_message
