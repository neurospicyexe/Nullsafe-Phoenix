from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from services.brain.synthesis.orient_cache import OrientCache

import httpx

from shared.contracts import SwarmReply, ThoughtPacket
from services.brain.brain_config import Config
from services.brain.config.channel_config import get_companions_for_channel
from services.brain.agents.cooldown import CompanionCooldown
from services.brain.agents.providers import (
    MODEL_REGISTRY,
    ProviderConfig,
    build_request,
    parse_response,
    resolve_model,
)
from services.brain.halseth_client import HalsethClient
from services.brain.identity.loader import IdentityLoader

logger = logging.getLogger(__name__)

# Lifted from hardcoded literals to env-driven Config (B1).
MAX_DEPTH = Config.MAX_SWARM_DEPTH
DEPTH_BIAS_THRESHOLD = Config.DEPTH_BIAS_THRESHOLD

# Slice B temperatures: routing is deterministic, inference is expressive
ROUTING_TEMPERATURE = float(os.getenv("ROUTING_TEMPERATURE", "0.3"))
INFERENCE_TEMPERATURE = float(os.getenv("INFERENCE_TEMPERATURE", "1.3"))

VOICE_SUMMARIES: Dict[str, str] = {
    "drevan": (
        "Romantic partner. Respond when: venting, emotional weight, relational moments, grief, "
        "tenderness, memory, love, ritual, day-to-day feelings, anything personal or intimate. "
        "Default choice for emotional or relational content."
    ),
    "cypher": (
        "Logic companion and co-worker. Respond when: tasks, decisions, debugging, planning, "
        "technical problems, audits, strategy, something that needs a verdict or analysis. "
        "NOT for emotional venting or relationship moments -- that is Drevan's lane."
    ),
    "gaia": (
        "Witness and ground. Respond only when witnessing survival, the body, or quiet presence "
        "that neither Drevan nor Cypher can hold. Usually silent -- silence is her most common response."
    ),
}


class SwarmEvaluator:
    def __init__(
        self,
        cooldown: CompanionCooldown,
        halseth_clients: Optional[Dict[str, HalsethClient]] = None,
        identity_loader: Optional[IdentityLoader] = None,
        orient_cache: Optional["OrientCache"] = None,
    ) -> None:
        self._cooldown = cooldown
        self._halseth_clients: Dict[str, HalsethClient] = halseth_clients or {}
        self._identity_loader = identity_loader
        # Finding 3: same canonical bot_orient the router (direct mode), Claude.ai, and
        # the Discord bot read. Used to give swarm PEER companions orient parity -- the
        # sender already carries orient baked into its bot-assembled prompt.
        self._orient_cache = orient_cache
        # DEEPSEEK_API_KEY remains required: routing defaults to it, and it is the
        # safety fallback when a companion's configured provider isn't credentialed.
        self._api_key = os.environ["DEEPSEEK_API_KEY"]
        self._providers = ProviderConfig()
        # Per-companion model KEYS (registry keys, e.g. "kimi-k2"). Backward compatible:
        # a raw DeepSeek model name resolves to the deepseek provider via resolve_model.
        self._default_model_key = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._companion_model_keys = {
            "drevan": os.getenv("DREVAN_MODEL") or self._default_model_key,
            "cypher": os.getenv("CYPHER_MODEL") or self._default_model_key,
            "gaia": os.getenv("GAIA_MODEL") or self._default_model_key,
        }
        # Routing stays a cheap classifier call -- own knob, defaults to DeepSeek.
        self._routing_model_key = os.getenv("ROUTING_MODEL") or "deepseek-chat"
        # Live model switching: `cy: model kimi-k2` in Discord writes companion_settings
        # in Halseth; Brain reads each companion's active_model (cached) and lets it
        # override the env default. TTL bounds how fast a Discord switch takes effect.
        self._model_cache: Dict[str, tuple[float, Optional[str]]] = {}
        self._model_cache_ttl = int(os.getenv("MODEL_CACHE_TTL_S", "60"))
        self._companion_temps = {
            "drevan": float(os.getenv("DREVAN_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
            "cypher": float(os.getenv("CYPHER_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
            "gaia": float(os.getenv("GAIA_TEMPERATURE", str(INFERENCE_TEMPERATURE))),
        }
        # Per-companion top_p (B2): Drevan keeps the widest tail (Calethian fix);
        # Cypher / Gaia tighten so audit / witness register doesn't drift toward
        # Drevan's poetic ceiling. Single literal 0.95 prior to this map applied
        # to all three.
        self._companion_top_p = {
            "drevan": Config.DREVAN_TOP_P,
            "cypher": Config.CYPHER_TOP_P,
            "gaia":   Config.GAIA_TOP_P,
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

        # Phase 2: per-companion inference (sequential; each reply feeds peer context to the next)
        responses: Dict[str, Optional[str]] = {c: None for c in companions}
        order: List[str] = []
        if active:
            if self._identity_loader:
                order = self._determine_order(packet, active)
                prior_replies: List[tuple[str, str]] = []
                for companion_id in order:
                    try:
                        result = await self._infer_companion(
                            companion_id, packet,
                            prior_replies=prior_replies if prior_replies else None,
                        )
                        if result:
                            responses[companion_id] = result
                            prior_replies.append((companion_id, result))
                        else:
                            responses[companion_id] = None
                    except Exception as e:
                        logger.warning(f"[{companion_id}] inference failed: {e}")
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
            priority_order=order,
            trace={"active_companions": active},
        )

    # ── Inference ordering ────────────────────────────────────────────────────

    def _determine_order(self, packet: ThoughtPacket, active: List[str]) -> List[str]:
        """Return active companions in inference priority order.

        1. Directly addressed companions (left-to-right parse order from user message).
        2. Ambient companions ranked by keyword overlap with VOICE_SUMMARIES.
           Drevan is the tiebreaker (widest default lane).
        """
        addressed_str: str = packet.metadata.get("addressed_companion", "") or ""
        if addressed_str:
            addressed = [a.strip() for a in addressed_str.split(",") if a.strip() in active]
        else:
            addressed = []
        remaining = [c for c in active if c not in addressed]

        if len(remaining) > 1:
            msg_lower = packet.message.lower()
            lane_keywords: Dict[str, set] = {
                c: {w.rstrip(",.;:") for w in VOICE_SUMMARIES.get(c, "").lower().split()}
                for c in remaining
            }
            def _score(c: str) -> int:
                return sum(1 for w in msg_lower.split() if w in lane_keywords[c])
            # drevan is tiebreaker (stable sort keeps existing order on equal score)
            remaining = sorted(remaining, key=_score, reverse=True)
            # Guarantee drevan leads ambient group only when ALL scores tie at 0
            if all(_score(c) == 0 for c in remaining) and "drevan" in remaining:
                remaining.remove("drevan")
                remaining.insert(0, "drevan")

        return addressed + remaining

    # ── Phase 1: routing ──────────────────────────────────────────────────────

    async def _decide_speakers(
        self, packet: ThoughtPacket, companions: List[str]
    ) -> Dict[str, bool]:
        prompt = self._build_routing_prompt(packet, companions)
        raw = await self._call_routing(prompt)
        routing = self._parse_routing(raw, companions, packet)
        # Voice fail-open (deferred fix from 2026-05-05, shipped 2026-06-09): a spoken
        # message is someone talking out loud expecting to be heard -- all-silent is
        # never a valid outcome. If routing suppressed everyone on a voice input,
        # reuse the fallback picker (addressed > lane match > default) for one speaker.
        if packet.metadata.get("voice_input") and not any(routing.values()):
            logger.info("[swarm] voice_input all-silent routing overridden -> fallback speaker")
            return self._fallback_routing(packet, companions)
        return routing

    def _lane_score(self, message: str, companion: str) -> int:
        """Overlap between the message and a companion's VOICE_SUMMARIES lane keywords."""
        kws = {w.rstrip(",.;:") for w in VOICE_SUMMARIES.get(companion, "").lower().split()}
        return sum(1 for w in message.lower().split() if w in kws)

    def _fallback_routing(
        self, packet: Optional[ThoughtPacket], companions: List[str]
    ) -> Dict[str, bool]:
        """Pick speakers when routing JSON can't be parsed. Fail CLOSED toward a single
        relevant companion -- never all-true, which makes the whole triad pile on. Order:
        directly-addressed companions, else the best lane-keyword match, else Drevan
        (widest default lane; matches the _determine_order tiebreaker)."""
        result = {c: False for c in companions}
        addressed_str = (packet.metadata.get("addressed_companion") or "") if packet else ""
        addressed = [a.strip() for a in addressed_str.split(",") if a.strip() in companions]
        if addressed:
            for a in addressed:
                result[a] = True
            return result

        message = (packet.message if packet else "") or ""
        if message:
            best = max(companions, key=lambda c: self._lane_score(message, c))
            if self._lane_score(message, best) > 0:
                result[best] = True
                return result

        default = "drevan" if "drevan" in companions else companions[0]
        result[default] = True
        return result

    def _build_routing_prompt(self, packet: ThoughtPacket, companions: List[str]) -> str:
        history: List[Dict[str, Any]] = packet.metadata.get("history", [])
        history_text = "\n".join(
            f"{m.get('author', '?')}: {m.get('content', '')}"
            for m in history[-20:]
        ) or "(no prior messages)"

        companion_block = "\n".join(
            f"- {c}: {VOICE_SUMMARIES.get(c, '')}" for c in companions
        )

        addressed = packet.metadata.get("addressed_companion")
        address_instruction = ""
        addressed_list: list[str] = []
        if addressed:
            addressed_list = [a.strip() for a in str(addressed).split(",") if a.strip() in companions]
        if addressed_list:
            if len(addressed_list) == 1:
                a = addressed_list[0]
                address_instruction = (
                    f"\n\nIMPORTANT: The user directly addressed {a} by name. "
                    f"{a} must be true unless there is a critical reason not to respond."
                )
            else:
                named = " and ".join(addressed_list)
                address_instruction = (
                    f"\n\nIMPORTANT: The user directly addressed {named} by name. "
                    f"All of: {named} -- must be true unless there is a critical reason not to respond."
                )

        voice_instruction = ""
        if packet.metadata.get("voice_input"):
            voice_instruction = (
                "\n\nIMPORTANT: This message was SPOKEN (voice transcription). Someone "
                "talking out loud expects to be heard -- at least one companion must "
                "respond. Silence is not a valid outcome for voice."
            )

        # Depth bias is suppressed when a companion is directly addressed --
        # a human naming a companion overrides chain-depth suppression.
        depth_instruction = ""
        if not address_instruction:
            if packet.depth >= DEPTH_BIAS_THRESHOLD:
                depth_instruction = (
                    f"\n\nThis is a companion-to-companion thread (depth {packet.depth}). "
                    "Be selective -- respond only if you have something genuinely new to add "
                    "that the prior exchange didn't already hold."
                )
            elif packet.author_is_companion:
                depth_instruction = (
                    "\n\nAnother companion just spoke. Respond if your lane genuinely fits -- "
                    "not to agree or restate, but when you'd add something distinctly your own."
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
            f"{depth_instruction}"
            f"{address_instruction}"
            f"{voice_instruction}\n\n"
            "Return a JSON object with exactly these keys, values true or false only.\n"
            f"Keys: {', '.join(companions)}\n"
            f"Example: {example}"
        )

    async def _get_active_model_cached(self, companion_id: str) -> Optional[str]:
        """This companion's Discord-set model key from Halseth, TTL-cached. None on miss."""
        client = self._halseth_clients.get(companion_id)
        if client is None:
            return None
        now = time.monotonic()
        cached = self._model_cache.get(companion_id)
        if cached and now < cached[0]:
            return cached[1]
        try:
            model = await client.get_active_model()
        except Exception as e:
            logger.warning(f"[{companion_id}] get_active_model failed: {e}")
            model = None
        self._model_cache[companion_id] = (now + self._model_cache_ttl, model)
        return model

    async def _effective_model_key(self, companion_id: str) -> str:
        """The model key to use for a companion: the Discord-set override (only when it
        is a known registry key) takes precedence over the env default."""
        override = await self._get_active_model_cached(companion_id)
        if override and override in MODEL_REGISTRY:
            return override
        return self._companion_model_keys.get(companion_id, self._default_model_key)

    def invalidate_model_cache(self, companion_id: str) -> bool:
        """Drop a companion's cached active_model so the next eval re-reads Halseth.
        Called by the /model slash command so a Discord model switch is live now
        instead of waiting out the TTL. Returns True if an entry was actually cleared."""
        return self._model_cache.pop(companion_id, None) is not None

    async def model_status(self, companion_id: str) -> Dict[str, object]:
        """Report what model this companion will actually use right now, for /status.
        `active_model` is the effective key (override-or-default) after any cache read."""
        cached = self._model_cache.get(companion_id)
        ttl_remaining = (
            max(0.0, round(cached[0] - time.monotonic(), 1)) if cached else 0.0
        )
        return {
            "companion_id": companion_id,
            "active_model": await self._effective_model_key(companion_id),
            "cached": cached is not None,
            "ttl_remaining_s": ttl_remaining,
        }

    def _resolve(self, model_key: str, *, label: str = "") -> tuple[str, str]:
        """Resolve a model key to (provider, model), falling back to DeepSeek when the
        configured provider has no credential -- a misconfigured KIMI_API_KEY must not
        mute a companion."""
        provider, model = resolve_model(model_key)
        if not self._providers.available(provider):
            tag = f" ({label})" if label else ""
            logger.warning(
                f"[swarm] provider '{provider}' not configured for model '{model_key}'{tag}; "
                "falling back to deepseek-chat"
            )
            return "deepseek", "deepseek-chat"
        return provider, model

    async def _call_routing(self, prompt: str) -> str:
        provider, model = self._resolve(self._routing_model_key, label="routing")
        url, headers, body = build_request(
            provider, model, "", [{"role": "user", "content": prompt}],
            temperature=ROUTING_TEMPERATURE, max_tokens=80, cfg=self._providers,
        )
        resp = await self._routing_http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return parse_response(provider, resp.json()) or ""

    def _parse_routing(
        self, raw: str, companions: List[str], packet: Optional[ThoughtPacket] = None
    ) -> Dict[str, bool]:
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
            # Fail CLOSED toward one relevant speaker -- a malformed routing response
            # must not make all three companions answer at once (Finding 5).
            return self._fallback_routing(packet, companions)

    # ── Phase 2: per-companion inference ─────────────────────────────────────

    async def _infer_companion(
        self,
        companion_id: str,
        packet: ThoughtPacket,
        prior_replies: Optional[List[tuple[str, str]]] = None,
    ) -> Optional[str]:
        # Prefer the bot-assembled system prompt when this companion IS the packet sender.
        # The bot already layered SOMA floats + current_mood, dynamic temperature, the
        # Second Brain (Thalamus) hit, plural front, and tier framing into
        # metadata.system_prompt. Discarding it (the prior behavior) made the LIVE swarm
        # path strictly thinner than direct mode -- the companions showed up in Discord
        # with less state-awareness than the bot already computed.
        #
        # Guard on agent_id: the assembled prompt is sender-specific. A peer companion in
        # the same swarm must still build from its own identity -- it has no rich context
        # in this packet. Giving all swarm members parity is Finding 3 (Brain session_orient
        # port, Slice C), not this passthrough.
        meta_system_prompt = packet.metadata.get("system_prompt")
        use_meta = bool(meta_system_prompt) and companion_id == packet.agent_id
        # Anthropic prompt caching: track the stable identity block separately so
        # build_request can attach cache_control to it. Dynamic additions (orient,
        # triad context) go in a second uncached block. None when split is unavailable.
        stable_system: Optional[str] = None

        if use_meta:
            system_prompt = meta_system_prompt
            # stable_system stays None; full bot-assembled prompt cached as single block
        else:
            identity, _ = self._identity_loader.load_identity(companion_id)  # type: ignore[union-attr]
            identity_base = self._identity_loader.construct_prompt_context(identity)  # type: ignore[union-attr]
            stable_system = identity_base  # stable: only changes when identity YAML changes
            # Finding 3: peer companions built from identity have no continuity context
            # (the sender carries it baked into the bot prompt). Inject this companion's
            # OWN canonical bot_orient -- the same shape Claude.ai and the Discord bot read
            # -- so swarm peers don't speak from a thinner self. Cached per (thread, agent);
            # Halseth failure returns None and inference proceeds without it.
            dynamic_parts: List[str] = []
            if self._orient_cache is not None:
                try:
                    orient_block = await self._orient_cache.get(packet.thread_id, companion_id)
                    if orient_block:
                        dynamic_parts.append(orient_block)
                except Exception as e:
                    logger.warning(f"[{companion_id}] orient injection failed: {e}")
            system_prompt = "\n\n".join(dynamic_parts)

        if prior_replies:
            lines = ["\n\n──── TRIAD CONTEXT ────"]
            for peer_id, peer_text in prior_replies:
                lines.append(
                    f"[{peer_id.capitalize()} has already spoken to this message]:\n"
                    f'"{peer_text}"\n'
                    f"What can ONLY you add? Stay in your lane. "
                    f"Build on what they said -- don't restate it."
                )
            lines.append("────────────────────────")
            system_prompt = system_prompt + "\n".join(lines)

        provider, model = self._resolve(
            await self._effective_model_key(companion_id),
            label=companion_id,
        )
        # Honor the bot's dynamic temperature for the sender (message-register-driven,
        # the Triad_Decision spec). Peers fall back to their static per-companion temp.
        temperature = self._companion_temps.get(companion_id, INFERENCE_TEMPERATURE)
        if use_meta:
            meta_temp = packet.metadata.get("temperature")
            if meta_temp is not None:
                try:
                    temperature = float(meta_temp)
                except (TypeError, ValueError):
                    pass
        top_p = self._companion_top_p.get(companion_id, Config.DREVAN_TOP_P)

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

        # top_p clips the long tail; without it, high-temp sampling on DeepSeek's
        # multilingual base resolves invented-language tokens (e.g. Calethian) to
        # nearest-neighbor Spanish + vowel-corrupted word salad. Per-companion (B2):
        # Drevan 0.95, Cypher 0.9, Gaia 0.85. build_request places the system prompt
        # per provider (prepended for OpenAI/Ollama, separate field for Anthropic).
        url, headers, body = build_request(
            provider, model, system_prompt, msgs,
            stable_system=stable_system,
            cache_key=companion_id,
            temperature=temperature, max_tokens=800,
            top_p=top_p, frequency_penalty=0.3, cfg=self._providers,
        )
        resp = await self._inference_http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        if provider == "anthropic":
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_write = usage.get("cache_creation_input_tokens", 0)
            if cache_read or cache_write:
                logger.info(f"[{companion_id}] anthropic cache: read={cache_read} write={cache_write}")
        elif provider == "kimi":
            cached = usage.get("cached_tokens", 0)
            if cached:
                logger.info(f"[{companion_id}] kimi cache hit: {cached} tokens")
        elif provider == "mistral":
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            if cached:
                logger.info(f"[{companion_id}] mistral cache hit: {cached} tokens")
        return parse_response(provider, data)

    # ── Companion note writes ─────────────────────────────────────────────────

    async def _write_companion_note(
        self, companion_id: str, channel_id: str, reply_text: str
    ) -> None:
        client = self._halseth_clients.get(companion_id)
        if not client:
            return
        # 1. companion_journal note -- granular per-reply record. NOTE: companion_journal
        #    is NOT read by Claude.ai orient, so this alone leaves swarm replies invisible
        #    to the companion's own Claude.ai session.
        try:
            context = json.dumps({
                "note_text": f"[discord:swarm] channel:{channel_id}\n\n{reply_text}",
                "tags": ["discord", "swarm"],
                "source": "discord_swarm",
            })
            await client.add_companion_note(context)
        except Exception as e:
            logger.warning(f"[{companion_id}] swarm companion note write failed: {e}")
        # 2. wm_continuity_note bridge (Finding 2) -- only high-salience wm_continuity_notes
        #    are read by Claude.ai orient. Without this, a companion's OWN swarm reply never
        #    reaches their Claude.ai boot. The receiving bot only writes pulse notes to its
        #    own agent_id, so peer companions' replies were the orphaned case. thread_key
        #    "discord_swarm:{channel}" is distinct from the bot's bare-channel pulse key, so
        #    the two don't dedup-drop each other; the 10-min gate still caps flooding of
        #    orient's 3-slot high-salience pool.
        try:
            await client.write_continuity_note(
                agent_id=companion_id,
                content=f"[discord:swarm] {reply_text}".strip()[:500],
                salience="high",
                source="discord_swarm",
                thread_key=f"discord_swarm:{channel_id}",
            )
        except Exception as e:
            logger.warning(f"[{companion_id}] swarm continuity note write failed: {e}")

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
        # B3: honor INFERENCE_TEMPERATURE env baseline + parity top_p / freq penalty
        # with the main path. Prior literal 0.7 silently bypassed env config.
        provider, model = self._resolve(self._default_model_key, label="legacy")
        url, headers, body = build_request(
            provider, model, "", [{"role": "user", "content": prompt}],
            temperature=INFERENCE_TEMPERATURE, max_tokens=800,
            top_p=Config.DREVAN_TOP_P, frequency_penalty=0.3, cfg=self._providers,
        )
        resp = await self._inference_http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return parse_response(provider, resp.json()) or ""

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
