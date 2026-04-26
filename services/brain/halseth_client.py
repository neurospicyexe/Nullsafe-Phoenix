#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python port of LibrarianClient (packages/shared/src/librarian.ts).

All Halseth reads/writes go through POST /librarian/mcp using JSON-RPC 2.0.
High-frequency writes use direct HTTP endpoints (stm, persona-blocks, human-blocks).
"""

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class HalsethClient:
    """
    Async client for Halseth Librarian API.

    All companion reads/writes route through /librarian/mcp (JSON-RPC 2.0).
    Direct HTTP is used only for fire-and-forget write paths (STM, blocks).
    """

    def __init__(self, url: str, secret: str, companion_id: str):
        self.url = url.rstrip("/")
        self.secret = secret
        self.companion_id = companion_id
        self._client = httpx.AsyncClient(timeout=20.0)

    async def _ask(self, request: str, context: Optional[str] = None, session_type: Optional[str] = None) -> dict:
        """
        Send a natural-language request to the Librarian.
        Returns parsed JSON result or raises on failure.
        """
        arguments: dict = {
            "request": request,
            "companion_id": self.companion_id,
        }
        if context:
            arguments["context"] = context
        if session_type:
            arguments["session_type"] = session_type

        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ask_librarian",
                "arguments": arguments,
            },
        })

        for attempt in range(2):
            try:
                res = await self._client.post(
                    f"{self.url}/librarian/mcp",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {self.secret}",
                    },
                )

                if res.status_code != 200:
                    if attempt == 0:
                        import asyncio
                        await asyncio.sleep(3)
                        continue
                    raise RuntimeError(f"Librarian {res.status_code}")

                content_type = res.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    raw = res.text
                    data_lines = [l for l in raw.split("\n") if l.startswith("data:")]
                    raw_body = data_lines[-1][5:].strip() if data_lines else "{}"
                else:
                    raw_body = res.text

                parsed = json.loads(raw_body)
                if "error" in parsed:
                    raise RuntimeError(f"Librarian error: {parsed['error'].get('message')}")

                text = parsed.get("result", {}).get("content", [{}])[0].get("text", "{}")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt == 0:
                    import asyncio
                    await asyncio.sleep(3)
                    continue
                logger.warning(f"[halseth] unreachable: {e}")
                return {}

        return {}

    async def bot_orient(self) -> Optional[dict]:
        """
        Fetch warm-boot context. Returns synthesis_summary, ground_threads,
        ground_handoff, rag_excerpts. Returns None on any failure.
        """
        try:
            result = await self._ask("bot orient")
            data = result.get("data")
            if not data:
                return None
            return {
                "synthesis_summary": data.get("synthesis_summary"),
                "ground_threads": data.get("ground_threads", []),
                "ground_handoff": data.get("ground_handoff"),
                "rag_excerpts": data.get("rag_excerpts", []),
            }
        except Exception as e:
            logger.warning(f"[halseth] bot_orient failed: {e}")
            return None

    async def session_open(self, session_type: str = "work") -> dict:
        return await self._ask("open my session", session_type=session_type)

    async def session_close(self, session_id: str, spine: str, last_real_thing: str, motion_state: str) -> dict:
        params = {
            "session_id": session_id,
            "spine": spine,
            "last_real_thing": last_real_thing,
            "motion_state": motion_state,
        }
        return await self._ask("close session", context=json.dumps(params))

    async def add_companion_note(self, note: str) -> dict:
        return await self._ask("add companion note", context=note)

    async def witness_log(self, entry: str, channel: Optional[str] = None) -> dict:
        return await self._ask("witness log", context=json.dumps({"entry": entry, "channel": channel}))

    async def synthesis_read(self) -> dict:
        """
        Read swarm data for synthesis loop.

        Makes five Librarian calls (sessions, feelings, notes, dreams, loops).
        Each call is independent -- partial failure returns what was readable.
        Returns dict with keys: sessions, feelings, notes, dreams, loops.
        """
        result: dict = {
            "sessions": [],
            "feelings": [],
            "tensions": [],
            "notes": [],
            "dreams": [],
            "loops": [],
        }

        # Sessions: recent 24h across the swarm
        try:
            sessions_resp = await self._ask(
                "get recent sessions for all companions in the last 24 hours for synthesis",
                context='{"hours": 24, "limit": 20}'
            )
            result["sessions"] = sessions_resp.get("data", {}).get("sessions", [])
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read sessions failed: {e}")

        # Feelings: recent emotional states across all companions
        try:
            feelings_resp = await self._ask(
                "get recent feelings for all companions",
                context='{"limit": 30}'
            )
            result["feelings"] = feelings_resp.get("data", {}).get("feelings", [])
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read feelings failed: {e}")

        # Notes: companion continuity notes
        try:
            notes_resp = await self._ask(
                "get recent companion notes for synthesis",
                context='{"limit": 50}'
            )
            result["notes"] = notes_resp.get("data", {}).get("notes", [])
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read notes failed: {e}")

        # Dreams: companion-owned aspirations (first-class for swarm_threads)
        try:
            dreams_resp = await self._ask(
                "get recent webmind dreams for all companions",
                context='{"limit": 20}'
            )
            result["dreams"] = dreams_resp.get("data", {}).get("dreams", [])
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read dreams failed: {e}")

        # Loops: recurring patterns (first-class for swarm_threads)
        try:
            loops_resp = await self._ask(
                "get recent webmind loops for all companions",
                context='{"limit": 20}'
            )
            result["loops"] = loops_resp.get("data", {}).get("loops", [])
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read loops failed: {e}")

        # Tensions: direct HTTP (GET /ingest/tensions) -- Librarian NL doesn't route here reliably
        try:
            tensions_res = await self._client.get(
                f"{self.url}/ingest/tensions",
                headers={"Authorization": f"Bearer {self.secret}"},
            )
            if tensions_res.status_code == 200:
                body = tensions_res.json()
                result["tensions"] = body if isinstance(body, list) else body.get("tensions", [])
            else:
                logger.warning(f"[halseth] synthesis_read tensions {tensions_res.status_code}")
        except Exception as e:
            logger.warning(f"[halseth] synthesis_read tensions failed: {e}")

        return result

    # ── Direct HTTP writes (not Librarian NL) ─────────────────────────────

    async def write_limbic_state(self, state: dict) -> Optional[dict]:
        """POST /mind/limbic -- write full LimbicState blob."""
        try:
            res = await self._client.post(
                f"{self.url}/mind/limbic",
                json=state,
                headers={"Authorization": f"Bearer {self.secret}"},
            )
            if res.status_code >= 300:
                logger.warning(f"[halseth] write_limbic_state {res.status_code}: {res.text[:200]}")
                return None
            return res.json()
        except Exception as e:
            logger.warning(f"[halseth] write_limbic_state failed: {e}")
            return None

    async def write_thread(self, thread_key: str, agent_id: str, title: str,
                           context: Optional[str] = None, source: str = "synthesis_loop") -> Optional[dict]:
        """POST /mind/thread -- upsert a mind thread."""
        body: dict = {
            "thread_key": thread_key,
            "agent_id": agent_id,
            "title": title,
            "status": "open",
            "source": source,
            "actor": "system",
        }
        if context:
            body["context"] = context
        try:
            res = await self._client.post(
                f"{self.url}/mind/thread",
                json=body,
                headers={"Authorization": f"Bearer {self.secret}"},
            )
            if res.status_code >= 300:
                logger.warning(f"[halseth] write_thread {res.status_code}: {res.text[:200]}")
                return None
            return res.json()
        except Exception as e:
            logger.warning(f"[halseth] write_thread failed: {e}")
            return None

    async def write_continuity_note(self, agent_id: str, content: str,
                                     salience: str = "high", source: str = "synthesis_loop") -> Optional[dict]:
        """POST /mind/note -- write a continuity note."""
        try:
            res = await self._client.post(
                f"{self.url}/mind/note",
                json={
                    "agent_id": agent_id,
                    "content": content,
                    "salience": salience,
                    "source": source,
                    "actor": "system",
                    "note_type": "continuity",
                },
                headers={"Authorization": f"Bearer {self.secret}"},
            )
            if res.status_code >= 300:
                logger.warning(f"[halseth] write_continuity_note {res.status_code}: {res.text[:200]}")
                return None
            return res.json()
        except Exception as e:
            logger.warning(f"[halseth] write_continuity_note failed: {e}")
            return None

    async def write_conclusion(
        self,
        companion_id: str,
        conclusion_text: str,
        confidence: float = 0.7,
        belief_type: str = "self",
        subject: Optional[str] = None,
        provenance: Optional[str] = None,
    ) -> Optional[dict]:
        """POST /companion-conclusions -- write a resolved conclusion."""
        VALID_BELIEF_TYPES = {"self", "observational", "relational", "systemic"}
        if belief_type not in VALID_BELIEF_TYPES:
            logger.warning(f"write_conclusion: invalid belief_type '{belief_type}', defaulting to 'self'")
            belief_type = "self"

        body: dict = {
            "companion_id": companion_id,
            "conclusion_text": conclusion_text,
            "confidence": confidence,
            "belief_type": belief_type,
        }
        if subject is not None:
            body["subject"] = subject
        if provenance is not None:
            body["provenance"] = provenance

        try:
            res = await self._client.post(
                f"{self.url}/companion-conclusions",
                json=body,
                headers={"Authorization": f"Bearer {self.secret}"},
            )
            if res.status_code >= 300:
                logger.warning(f"[halseth] write_conclusion {res.status_code}: {res.text[:200]}")
                return None
            return res.json()
        except Exception as e:
            logger.warning(f"[halseth] write_conclusion failed: {e}")
            return None

    async def stm_write(self, channel_id: str, role: str, content: str, author_name: Optional[str] = None) -> None:
        """Fire-and-forget STM write. Caller should catch exceptions."""
        res = await self._client.post(
            f"{self.url}/stm/entries",
            json={
                "companion_id": self.companion_id,
                "channel_id": channel_id,
                "role": role,
                "content": content,
                "author_name": author_name,
            },
            headers={"Authorization": f"Bearer {self.secret}"},
        )
        if res.status_code >= 300:
            raise RuntimeError(f"stm_write {res.status_code}")

    async def stm_load(self, channel_id: str, limit: int = 30) -> list:
        res = await self._client.get(
            f"{self.url}/stm/entries",
            params={"companion_id": self.companion_id, "channel_id": channel_id, "limit": limit},
            headers={"Authorization": f"Bearer {self.secret}"},
        )
        if res.status_code >= 300:
            raise RuntimeError(f"stm_load {res.status_code}")
        return res.json().get("entries", [])

    async def close(self) -> None:
        await self._client.aclose()


def format_orient_context(orient: Optional[dict]) -> str:
    """
    Format a bot_orient result into a compact context block (~1400 chars max).
    Mirrors formatRecentContext() from librarian.ts.
    """
    if not orient:
        return ""

    parts = []
    if orient.get("synthesis_summary"):
        parts.append(f"## Recent\n{orient['synthesis_summary'][:600]}")
    if orient.get("ground_handoff"):
        parts.append(f"## Last handoff\n{orient['ground_handoff'][:200]}")
    if orient.get("ground_threads"):
        parts.append(f"## Open threads\n{' / '.join(orient['ground_threads'])}")
    if orient.get("rag_excerpts"):
        parts.append(f"## Historical resonance\n{chr(10).join(orient['rag_excerpts'])[:300]}")

    return "\n\n".join(parts)[:1400]
