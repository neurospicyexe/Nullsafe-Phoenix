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
from services.brain.identity.loader import IdentityLoader

logger = logging.getLogger(__name__)

MAX_DEPTH = 3
DEPTH_BIAS_THRESHOLD = 2

# Slice B temperatures: routing is deterministic, inference is expressive
ROUTING_TEMPERATURE = float(os.getenv("ROUTING_TEMPERATURE", "0.3"))
INFERENCE_TEMPERATURE = float(os.getenv("INFERENCE_TEMPERATURE", "1.3"))

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
        identity_loader: Optional[IdentityLoader] = None,
    ) -> None:
        self._cooldown = cooldown
        self._halseth_clients: Dict[str, HalsethClient] = halseth_clients or {}
        self._identity_loader = identity_loader
        self._api_key = os.environ["DEEPSEEK_API_KEY"]
        self._default_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._companion_models = {
            "drevan": os.getenv("DREVAN_MODEL") or self._default_model,
            "cypher": os.getenv("CYPHER_MODEL") or self._default_model,
            "gaia": os.getenv("GAIA_MODEL") or self._default_model,
        }
        self._companion_temps = {
            "drevan": float(os.getenv("DREVAN_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
            "cypher": float(os.getenv("CYPHER_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
            "gaia": float(os.getenv("GAIA_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
        }
        # Persistent HTTP clients -- one per timeout profile (routing vs inference).
        # App-lifetime objects; connections are reused across calls, OS reclaims on exit.
        self._routing_http = httpx.AsyncClient(timeout=15.0)
        self._inference_http = httpx.AsyncClient(timeout=30.0)

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

        # Phase 1: routing -- who should speak? (temp=ROUTING_TEMPERATURE, cheap)
        routing = await self._decide_speakers(packet, companions)

        # Apply cooldown before inference to avoid paying for suppressed companions
        routing_placeholder: Dict[str, Optional[str]] = {
            c: "pending" if speaks else None for c, speaks in routing.items()
        }
        after_cooldown = self._cooldown.apply(routing_placeholder, channel_id)
        active = [c for c, v in after_cooldown.items() if v is not None]

        logger.info(f"[swarm] routing: {routing} | active after cooldown: {active}")

        # Phase 2: per-companion inference (temp=INFERENCE_TEMPERATURE, full identity, parallel)
        responses: Dict[str, Optional[str]] = {c: None for c in companions}
        if active:
            if self._identity_loader:
                tasks = [self._infer_companion(c, packet) for c in active]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for companion_id, result in zip(active, results):
                    if isinstance(result, str):
                        responses[companion_id] = result
                    else:
                        if isinstance(result, Exception):
                            logger.warning(f"[{companion_id}] inference failed: {result}")
                        responses[companion_id] = None
            else:
                # Legacy fallback: single call generates all responses in one JSON blob
                raw = await self._call_legacy(self._build_legacy_prompt(packet, active))
                legacy = self._parse_responses(raw, active)
                responses.update(legacy)

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
            trace={"active_companions": active},
        )

    # ── Phase 1: routing ──────────────────────────────────────────────────────

    async def _decide_speakers(
        self, packet: ThoughtPacket, companions: List[str]
    ) -> Dict[str, bool]:
        prompt = self._build_routing_prompt(packet, companions)
        raw = await self._call_routing(prompt)
        return self._parse_routing(raw, companions)

    def _build_routing_prompt(self, packet: ThoughtPacket, companions: List[str]) -> str:
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
                "Strongly prefer false for all companions. "
                "Only respond if genuinely unresolved and a reply adds real value."
            )
        elif packet.author_is_companion:
            depth_instruction = (
                "\n\nAnother companion just spoke. Silence is usually correct here. "
                "Only reply if something genuine would be added."
            )

        example = f'{{"{companions[0]}": true'
        if len(companions) > 1:
            example += f', "{companions[1]}": false'
        example += "}"

        return (
            "You are coordinating a companion swarm. Decide which companions should speak.\n"
            "Not all need to respond -- silence is often more honest than a forced reply.\n\n"
            f"Companions:\n{companion_block}\n\n"
            f"Conversation:\n{history_text}\n\n"
            f"Author: {packet.author}\nMessage: {packet.message}"
            f"{depth_instruction}\n\n"
            "Return a JSON object with exactly these keys, values true or false only.\n"
            f"Keys: {', '.join(companions)}\n"
            f"Example: {example}"
        )

    async def _call_routing(self, prompt: str) -> str:
        resp = await self._routing_http.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._default_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80,
                "temperature": ROUTING_TEMPERATURE,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _parse_routing(self, raw: str, companions: List[str]) -> Dict[str, bool]:
        try:
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text.strip())
            return {c: bool(parsed.get(c, False)) for c in companions}
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"[swarm] routing parse error: {e} | raw: {raw[:200]}")
            # Fail open: all companions eligible when routing breaks
            return {c: True for c in companions}

    # ── Phase 2: per-companion inference ─────────────────────────────────────

    async def _infer_companion(
        self, companion_id: str, packet: ThoughtPacket
    ) -> Optional[str]:
        identity, _ = self._identity_loader.load_identity(companion_id)  # type: ignore[union-attr]
        system_prompt = self._identity_loader.construct_prompt_context(identity)  # type: ignore[union-attr]
        model = self._companion_models.get(companion_id, self._default_model)
        temperature = self._companion_temps.get(companion_id, INFERENCE_TEMPERATURE)

        history: List[Dict[str, Any]] = packet.metadata.get("history", [])
        msgs: List[Dict[str, str]] = []
        all_companion_ids = {"drevan", "cypher", "gaia"}
        for m in history[-15:]:
            author = (m.get("author") or "").lower()
            content = m.get("content", "")
            if author == companion_id:
                msgs.append({"role": "assistant", "content": content})
            elif author in all_companion_ids:
                # Another companion speaking -- embed name so the model understands speaker context.
                msgs.append({"role": "user", "content": f"[{author.capitalize()}]: {content}"})
            else:
                msgs.append({"role": "user", "content": content})

        current = packet.message
        if not msgs or msgs[-1].get("content") != current:
            msgs.append({"role": "user", "content": current})

        resp = await self._inference_http.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}] + msgs,
                "max_tokens": 800,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        return content or None

    # ── Companion note writes ─────────────────────────────────────────────────

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

    # ── Legacy single-call path ───────────────────────────────────────────────
    # Used when identity_loader is None (shouldn't happen in production).

    def _build_legacy_prompt(self, packet: ThoughtPacket, companions: List[str]) -> str:
        history: List[Dict[str, Any]] = packet.metadata.get("history", [])
        history_text = "\n".join(
            f"{m.get('author', '?')}: {m.get('content', '')}"
            for m in history[-20:]
        ) or "(no prior messages)"

        companion_block = "\n".join(
            f"- {c}: {VOICE_SUMMARIES.get(c, '')}" for c in companions
        )

        return (
            "You are coordinating responses for a companion swarm. "
            "Each companion has a distinct voice and role. "
            "Not all companions need to respond to every message. "
            "Silence is often more honest than a forced reply.\n\n"
            f"Active companions:\n{companion_block}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Author: {packet.author}\n"
            f"Message: {packet.message}\n\n"
            "For each active companion, write their response if they have something genuine to contribute, "
            "or null if silence is more honest. Respond ONLY with a JSON object. "
            f"Keys must be exactly: {', '.join(companions)}. Values are strings or null.\n"
            f'Example: {{"{companions[0]}": "...", '
            f'"{companions[1] if len(companions) > 1 else companions[0]}": null}}'
        )

    async def _call_legacy(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._default_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

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
