#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SecondBrainClient -- Thalamus pattern for Brain.

Proxies Second Brain semantic search through Halseth's /mind/search endpoint.
Same transport chain Discord bots use (LibrarianClient.searchForMessage in
nullsafe-discord/packages/shared/src/librarian.ts). Halseth handles MCP
session management against Second Brain so Brain only needs an HTTP client.

Contract from identity yaml VAULT ACCESS block:
  "Every message >=20 chars triggers automatic vault search; results pre-load
   as [Memory -- Second Brain retrieved for this message: ...] in your context."

This client implements the search side of that contract. The router decides
when to call it and how to inject the result into the system prompt.

v0 scope: search only. Vault writes are not in this client -- Brain's writes
all flow to Halseth, and Second Brain ingestion is driven by separate workers.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Mirrors the identity yaml threshold ("every message >=20 chars triggers
# automatic vault search") and Discord's Thalamus default. Short messages
# are mostly acknowledgments and route badly through semantic search.
DEFAULT_MIN_QUERY_CHARS = 20

# Mirrors Discord LibrarianClient timeout (6_000 ms). Short enough to overlap
# with the inference setup cost; long enough that warm SB usually responds.
DEFAULT_TIMEOUT_SECONDS = 6.0

# Halseth caps query at 500 chars; we trim defensively before sending.
MAX_QUERY_CHARS = 500


class SecondBrainClient:
    """Thin client over halseth's /mind/search proxy to Second Brain."""

    def __init__(
        self,
        halseth_url: str,
        secret: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        min_query_chars: int = DEFAULT_MIN_QUERY_CHARS,
    ):
        if not halseth_url:
            raise ValueError("SecondBrainClient requires halseth_url")
        if not secret:
            raise ValueError("SecondBrainClient requires secret")
        self._url = halseth_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._min_query_chars = min_query_chars

    async def search_for_message(
        self,
        query: str,
        agent_id: str,
    ) -> Optional[str]:
        """
        Returns the raw sb_search result string (JSON-encoded chunks payload),
        or None if the search was skipped, missed, or errored.

        The Brain identity contract says callers should prepend the result
        as `[Memory -- Second Brain retrieved for this message: <result>]`
        into the system prompt. Returning the raw string lets the caller
        decide how to wrap it.

        Never raises. A miss/error returns None so Brain inference proceeds
        without vault context rather than failing the whole turn.
        """
        if not query or not isinstance(query, str):
            return None
        trimmed = query.strip()
        if len(trimmed) < self._min_query_chars:
            return None
        # Defensive trim -- halseth will 400 if we exceed the cap.
        if len(trimmed) > MAX_QUERY_CHARS:
            trimmed = trimmed[:MAX_QUERY_CHARS]

        if agent_id not in ("drevan", "cypher", "gaia"):
            # Halseth would reject the agent_id binding; skip rather than 4xx.
            logger.debug(f"[sb] skip search: invalid agent_id={agent_id!r}")
            return None

        url = f"{self._url}/mind/search"
        params = {"query": trimmed, "agent_id": agent_id}
        headers = {"Authorization": f"Bearer {self._secret}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.get(url, params=params, headers=headers)
            if res.status_code != 200:
                logger.debug(f"[sb] non-200 from /mind/search: {res.status_code}")
                return None
            payload = res.json()
            if not isinstance(payload, dict):
                logger.debug(f"[sb] /mind/search returned non-dict body: {type(payload)}")
                return None
            result = payload.get("result")
            if result is None:
                return None
            if not isinstance(result, str):
                logger.debug(f"[sb] /mind/search result was not a string: {type(result)}")
                return None
            return result if result.strip() else None
        except httpx.TimeoutException:
            logger.debug(f"[sb] /mind/search timeout after {self._timeout}s")
            return None
        except Exception as e:
            logger.warning(f"[sb] /mind/search failed: {e}")
            return None


def format_vault_injection(raw_result: str) -> str:
    """
    Wrap a raw sb_search result string in the identity-contract envelope so it
    can be appended to the system prompt verbatim. Matches the format identity
    yamls already announce to companions:

      [Memory -- Second Brain retrieved for this message: ...]

    Length is capped at ~3000 chars so a large vault hit doesn't blow the
    context window (DeepSeek context is generous but still finite).
    """
    if not raw_result:
        return ""
    body = raw_result.strip()
    MAX_INJECTION = 3000
    if len(body) > MAX_INJECTION:
        body = body[:MAX_INJECTION] + " […vault excerpt truncated to fit context]"
    return f"\n\n[Memory -- Second Brain retrieved for this message: {body}]"
