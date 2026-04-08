#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brain -> WebMind HTTP client.

Used by the synthesis loop to write LimbicState records and continuity notes,
and by the orient cache to read current limbic state.
Never raises -- returns None/[] on any failure. Caller handles graceful degradation.
HTTP 5xx errors are logged at ERROR level; network/timeout failures at WARNING.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _log_http_failure(method: str, status_code: int, detail: str) -> None:
    """Log HTTP failures: 5xx as error (service down), others as warning."""
    if status_code >= 500:
        logger.error(f"[webmind] {method} server error {status_code}: {detail}")
    else:
        logger.warning(f"[webmind] {method} failed {status_code}: {detail}")


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
                if not resp.is_success:
                    _log_http_failure("write_limbic_state", resp.status_code, resp.text[:200])
                    return None
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] write_limbic_state network error: {e}")
            return None

    async def get_current_limbic_state(self) -> Optional[dict]:
        """GET /mind/limbic/current -- return most recent LimbicState or None."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._url}/mind/limbic/current")
                if resp.status_code == 404:
                    return None
                if not resp.is_success:
                    _log_http_failure("get_current_limbic_state", resp.status_code, resp.text[:200])
                    return None
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] get_current_limbic_state network error: {e}")
            return None

    async def write_note(self, note_dict: dict) -> Optional[dict]:
        """POST /mind/notes -- write a continuity note."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._url}/mind/notes", json=note_dict)
                if not resp.is_success:
                    _log_http_failure("write_note", resp.status_code, resp.text[:200])
                    return None
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] write_note network error: {e}")
            return None

    async def get_notes(self, agent_id: str, limit: int = 10) -> list:
        """GET /mind/notes -- return recent notes for an agent."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._url}/mind/notes",
                    params={"agent_id": agent_id, "limit": limit},
                )
                if not resp.is_success:
                    _log_http_failure("get_notes", resp.status_code, resp.text[:200])
                    return []
                return resp.json().get("notes", [])
        except Exception as e:
            logger.warning(f"[webmind] get_notes network error: {e}")
            return []

    async def get_orient(self, agent_id: str) -> Optional[dict]:
        """GET /mind/orient -- return limbic state + recent notes for an agent."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._url}/mind/orient",
                    params={"agent_id": agent_id},
                )
                if not resp.is_success:
                    _log_http_failure("get_orient", resp.status_code, resp.text[:200])
                    return None
                return resp.json()
        except Exception as e:
            logger.warning(f"[webmind] get_orient network error: {e}")
            return None
