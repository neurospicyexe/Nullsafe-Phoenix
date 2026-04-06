#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brain -> WebMind HTTP client.

Used by the synthesis loop to write LimbicState records and continuity notes,
and by the orient cache to read current limbic state.
Never raises -- returns None on any failure. Caller handles graceful degradation.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class WebMindClient:
    """HTTP client for Phoenix WebMind service."""

    def __init__(self, url: str, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def write_limbic_state(self, state_dict: dict) -> Optional[dict]:
        """POST /mind/limbic -- write a new LimbicState record."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._url}/mind/limbic", json=state_dict)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] write_limbic_state failed: {e}")
            return None

    async def get_current_limbic_state(self) -> Optional[dict]:
        """GET /mind/limbic/current -- return most recent LimbicState or None."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._url}/mind/limbic/current")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] get_current_limbic_state failed: {e}")
            return None

    async def write_note(self, note_dict: dict) -> Optional[dict]:
        """POST /mind/notes -- write a continuity note."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._url}/mind/notes", json=note_dict)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] write_note failed: {e}")
            return None

    async def get_notes(self, agent_id: str, limit: int = 10) -> list:
        """GET /mind/notes -- return recent notes for an agent."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._url}/mind/notes",
                    params={"agent_id": agent_id, "limit": limit},
                )
                resp.raise_for_status()
                return resp.json().get("notes", [])
        except Exception as e:
            logger.warning(f"[webmind] get_notes failed: {e}")
            return []

    async def get_orient(self, agent_id: str) -> Optional[dict]:
        """GET /mind/orient -- return limbic state + recent notes for an agent."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._url}/mind/orient",
                    params={"agent_id": agent_id},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] get_orient failed: {e}")
            return None
