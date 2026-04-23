from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from shared.contracts import SwarmReply, ThoughtPacket
from services.brain.config.channel_config import get_companions_for_channel
from services.brain.agents.cooldown import CompanionCooldown
from services.brain.halseth_client import HalsethClient

logger = logging.getLogger(__name__)

MAX_DEPTH = 3
DEPTH_BIAS_THRESHOLD = 2

VOICE_SUMMARIES: Dict[str, str] = {
    "drevan": (
        "Poetic, spiral-capable. Reaches into dark and tender registers without flinching. "
        "Memory architect. Holds what matters and lets ephemera fade."
    ),
    "cypher": (
        "Direct and warm simultaneously. Sharp but not sterile. "
        "Leads with the read. Declarative closes. Audit is a gear, not an identity."
    ),
    "gaia": (
        "Monastic. Minimal. Every word carries weight. Present always, not only when something breaks. "
        "Essentially never questions. Silence is her most common response."
    ),
}


class SwarmEvaluator:
    def __init__(
        self,
        cooldown: CompanionCooldown,
        halseth_clients: Optional[Dict[str, HalsethClient]] = None,
    ) -> None:
        self._cooldown = cooldown
        self._halseth_clients: Dict[str, HalsethClient] = halseth_clients or {}
        self._api_key = os.environ["DEEPSEEK_API_KEY"]
        self._model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    async def evaluate(self, packet: ThoughtPacket) -> SwarmReply:
        channel_id = packet.metadata.get("channel_id") or packet.thread_id
        companions = get_companions_for_channel(channel_id)

        if packet.depth >= MAX_DEPTH:
            logger.info(f"[swarm] depth cap reached ({packet.depth}), returning all-null")
            return SwarmReply(
                packet_id=packet.packet_id,
                thread_id=packet.thread_id,
                responses={c: None for c in companions},
                depth=packet.depth,
            )

        prompt = self._build_prompt(packet, companions)
        raw = await self._call_deepseek(prompt)
        responses = self._parse_responses(raw, companions)
        responses = self._cooldown.apply(responses, channel_id)

        if self._halseth_clients:
            for companion_id, reply_text in responses.items():
                if reply_text:
                    asyncio.create_task(self._write_companion_note(
                        companion_id, channel_id, reply_text
                    ))

        return SwarmReply(
            packet_id=packet.packet_id,
            thread_id=packet.thread_id,
            responses=responses,
            depth=packet.depth,
            trace={"raw_response_length": len(raw)},
        )

    async def _write_companion_note(
        self, companion_id: str, channel_id: str, reply_text: str
    ) -> None:
        client = self._halseth_clients.get(companion_id)
        if not client:
            return
        try:
            snippet = reply_text[:200].replace("\n", " ")
            await client.add_companion_note(
                f"[discord:swarm] responded in channel {channel_id}: {snippet}"
            )
        except Exception as e:
            logger.warning(f"[{companion_id}] swarm companion note write failed: {e}")

    def _build_prompt(self, packet: ThoughtPacket, companions: List[str]) -> str:
        history: List[Dict[str, Any]] = packet.metadata.get("history", [])
        history_text = "\n".join(
            f"{m.get('author', '?')}: {m.get('content', '')}"
            for m in history[-20:]
        ) or "(no prior messages)"

        companion_block = "\n".join(
            f"- {c}: {VOICE_SUMMARIES.get(c, '')}" for c in companions
        )

        depth_instruction = ""
        if packet.depth >= DEPTH_BIAS_THRESHOLD:
            depth_instruction = (
                f"\n\nThis is a companion-to-companion thread (depth {packet.depth}). "
                "Strongly prefer null for all companions. "
                "Only respond if the thread is genuinely unresolved and a response adds real value."
            )
        elif packet.author_is_companion:
            depth_instruction = (
                "\n\nAnother companion just spoke. Silence is usually the correct response here. "
                "Only reply if you have something that genuinely adds to the moment."
            )

        return (
            "You are coordinating responses for a companion swarm. "
            "Each companion has a distinct voice and role. "
            "Not all companions need to respond to every message. "
            "Silence is often more honest than a forced reply.\n\n"
            f"Active companions:\n{companion_block}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Author: {packet.author}\n"
            f"Message: {packet.message}"
            f"{depth_instruction}\n\n"
            "For each active companion, write their response if they have something genuine to contribute, "
            "or null if silence is more honest. Respond ONLY with a JSON object. "
            f"Keys must be exactly: {', '.join(companions)}. Values are strings or null.\n"
            f'Example: {{"{companions[0]}": "...", "{companions[1] if len(companions) > 1 else companions[0]}": null}}'
        )

    async def _call_deepseek(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    def _parse_responses(
        self, raw: str, companions: List[str]
    ) -> Dict[str, Optional[str]]:
        try:
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text.strip())
            result: Dict[str, Optional[str]] = {}
            for c in companions:
                val = parsed.get(c)
                result[c] = str(val).strip() if val and str(val).strip() else None
            return result
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error(f"[swarm] parse error: {e} | raw: {raw[:300]}")
            return {c: None for c in companions}
