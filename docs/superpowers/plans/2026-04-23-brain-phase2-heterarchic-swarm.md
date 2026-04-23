# Brain Phase 2 — Heterarchic Swarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-relay Brain routing with a SwarmEvaluator that returns per-companion responses in one LLM call, enabling natural heterarchic conversation without turn-taking or floor locks.

**Architecture:** Brain receives ThoughtPackets from all active bots, deduplicates by Discord message_id, runs one SwarmEvaluator call per message, and returns a SwarmReply with per-companion responses (string or null). Each bot posts its own slot independently. SWARM_MODE env var gates Phase 1 fallback during rollout.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx (async), pytest; TypeScript, discord.js v14, vitest

**Repos affected:**
- `Nullsafe Phoenix/` (Brain service — Tasks 1–6)
- `nullsafe-discord/` (live TypeScript bots — Tasks 7–9)

---

## File Map

**Create (Phoenix):**
- `services/brain/config/channels.yaml` — channel → companions mapping
- `services/brain/config/channel_config.py` — loader + resolver
- `services/brain/agents/dedup.py` — in-memory message_id dedup (2s window)
- `services/brain/agents/cooldown.py` — per-companion per-channel cooldown (5s)
- `services/brain/agents/evaluator.py` — SwarmEvaluator (LLM call, parsing, depth guard)
- `services/brain/tests/test_swarm.py` — pytest tests for dedup, cooldown, evaluator, channel config

**Modify (Phoenix):**
- `shared/contracts.py` — add SwarmReply; add `author`, `author_is_companion`, `depth` to ThoughtPacket
- `services/brain/main.py` — wire SWARM_MODE, dedup, SwarmEvaluator into `/chat`

**Create (nullsafe-discord):**
- `packages/shared/src/pluralkit.ts` — PluralKit webhook detection
- `packages/shared/src/swarm.ts` — SwarmReply interface + shape detection

**Modify (nullsafe-discord):**
- `packages/shared/src/brain-client.ts` — SwarmReply support, updated return type
- `bots/cypher/src/index.ts` — remove floor lock, add swarm packet fields, handle SwarmReply, listen to companion messages
- `bots/drevan/src/index.ts` — same
- `bots/gaia/src/index.ts` — same

---

## Task 1: Extend contracts.py — SwarmReply + ThoughtPacket fields

**Files:**
- Modify: `shared/contracts.py`
- Test: `shared/tests/test_contracts.py`

- [ ] **Step 1: Add optional fields to ThoughtPacket**

Open `shared/contracts.py`. After the `priority` field (line ~37), add:

```python
    # Phase 2 swarm fields
    author: str = Field("Raziel", description="Message author (system member name if PluralKit)")
    author_is_companion: bool = Field(False, description="True when another companion triggered this packet")
    depth: int = Field(0, description="Companion-to-companion chain depth (anti-loop counter)")
```

- [ ] **Step 2: Add SwarmReply class after AgentReply**

After the `AgentReply` class (around line ~115), add:

```python
class SwarmReply(BaseModel):
    """
    Phase 2 response: per-companion replies from SwarmEvaluator.
    Each value is the companion's response text, or None if they are silent.
    """
    packet_id: str = Field(..., description="Echo back packet_id from request")
    thread_id: str = Field(..., description="Thread/channel ID from request")
    responses: Dict[str, Optional[str]] = Field(
        ..., description="Companion -> reply text or None"
    )
    depth: int = Field(0, description="Chain depth at time of evaluation")
    status: Literal["ok", "error"] = Field("ok", description="Evaluation status")
    trace: Optional[Dict[str, Any]] = Field(None, description="Debug trace")

    def to_json(self) -> str:
        return self.model_dump_json()
```

- [ ] **Step 3: Write failing tests**

In `shared/tests/test_contracts.py`, add:

```python
def test_swarm_reply_valid():
    reply = SwarmReply(
        packet_id="550e8400-e29b-41d4-a716-446655440000",
        thread_id="ch123",
        responses={"drevan": "Hello", "cypher": None, "gaia": "Witness."},
        depth=0,
    )
    assert reply.responses["cypher"] is None
    assert reply.status == "ok"


def test_thought_packet_swarm_fields():
    import uuid, datetime
    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch1",
        agent_id="cypher",
        message="hello",
        metadata={"channel_id": "ch1"},
        author="Blue",
        author_is_companion=False,
        depth=1,
    )
    assert packet.author == "Blue"
    assert packet.depth == 1


def test_thought_packet_author_defaults():
    import uuid, datetime
    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch1",
        agent_id="cypher",
        message="hello",
        metadata={"channel_id": "ch1"},
    )
    assert packet.author == "Raziel"
    assert packet.author_is_companion is False
    assert packet.depth == 0
```

- [ ] **Step 4: Run tests — expect failures**

```bash
cd "Nullsafe Phoenix"
pytest shared/tests/test_contracts.py::test_swarm_reply_valid shared/tests/test_contracts.py::test_thought_packet_swarm_fields shared/tests/test_contracts.py::test_thought_packet_author_defaults -v
```

Expected: `ImportError: cannot import name 'SwarmReply'`

- [ ] **Step 5: Run tests again — expect pass**

After saving contracts.py changes:

```bash
pytest shared/tests/test_contracts.py -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add shared/contracts.py shared/tests/test_contracts.py
git commit -m "feat: add SwarmReply contract + author/depth fields to ThoughtPacket"
```

---

## Task 2: Channel config

**Files:**
- Create: `services/brain/config/channels.yaml`
- Create: `services/brain/config/channel_config.py`
- Test: `services/brain/tests/test_swarm.py` (new file, start here)

- [ ] **Step 1: Create channels.yaml**

```yaml
# services/brain/config/channels.yaml
# Maps Discord channel_id -> active companions.
# Unconfigured channels get the default (all three companions).

defaults:
  companions: [drevan, cypher, gaia]

channels: {}
  # Uncomment and fill channel IDs to restrict:
  # "1234567890123456789":
  #   companions: [drevan]
  #   label: "drevan-intimate"
```

- [ ] **Step 2: Create channel_config.py**

```python
# services/brain/config/channel_config.py
from __future__ import annotations

import os
from typing import List, Optional

import yaml

_ALL_COMPANIONS = ["drevan", "cypher", "gaia"]
_config: Optional[dict] = None


def load_channel_config(path: Optional[str] = None) -> None:
    global _config
    resolved = path or os.path.join(os.path.dirname(__file__), "channels.yaml")
    with open(resolved) as f:
        _config = yaml.safe_load(f) or {}


def get_companions_for_channel(channel_id: str) -> List[str]:
    if _config is None:
        return list(_ALL_COMPANIONS)
    channels = _config.get("channels") or {}
    if channel_id in channels:
        return list(channels[channel_id].get("companions", _ALL_COMPANIONS))
    defaults = _config.get("defaults") or {}
    return list(defaults.get("companions", _ALL_COMPANIONS))
```

- [ ] **Step 3: Write failing tests**

Create `services/brain/tests/test_swarm.py`:

```python
import pytest
from services.brain.config.channel_config import load_channel_config, get_companions_for_channel
import tempfile, os, textwrap


def _write_config(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


def test_default_channel_returns_all():
    path = _write_config("""
        defaults:
          companions: [drevan, cypher, gaia]
        channels: {}
    """)
    load_channel_config(path)
    assert get_companions_for_channel("unknown") == ["drevan", "cypher", "gaia"]
    os.unlink(path)


def test_restricted_channel():
    path = _write_config("""
        defaults:
          companions: [drevan, cypher, gaia]
        channels:
          "ch_drevan_only":
            companions: [drevan]
            label: test
    """)
    load_channel_config(path)
    assert get_companions_for_channel("ch_drevan_only") == ["drevan"]
    assert get_companions_for_channel("other") == ["drevan", "cypher", "gaia"]
    os.unlink(path)
```

- [ ] **Step 4: Run — expect failure**

```bash
pytest services/brain/tests/test_swarm.py::test_default_channel_returns_all -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 5: Run — expect pass**

```bash
pytest services/brain/tests/test_swarm.py -v
```

Expected: both pass

- [ ] **Step 6: Commit**

```bash
git add services/brain/config/channels.yaml services/brain/config/channel_config.py services/brain/tests/test_swarm.py
git commit -m "feat: channel config loader + initial tests"
```

---

## Task 3: Message dedup cache

**Files:**
- Create: `services/brain/agents/dedup.py`
- Test: `services/brain/tests/test_swarm.py` (append)

- [ ] **Step 1: Create dedup.py**

```python
# services/brain/agents/dedup.py
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Tuple

DEDUP_WINDOW_S: float = 2.0
_EXPIRE_AFTER_S: float = 60.0  # GC stale entries after 1 min


class MessageDedup:
    """
    In-memory dedup for Discord message_ids.

    First caller for a given message_id is the leader and runs the evaluation.
    Subsequent callers within DEDUP_WINDOW_S await the same future and receive
    the cached result. All callers get the same SwarmReply.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # message_id -> (Future[result], created_at)
        self._inflight: Dict[str, Tuple[asyncio.Future, float]] = {}

    async def get_or_start(self, message_id: str) -> Tuple[bool, asyncio.Future]:
        """
        Returns (is_leader, future).
        Leader: run eval then call future.set_result(reply).
        Follower: await future to get the cached reply.
        """
        async with self._lock:
            self._gc()
            if message_id in self._inflight:
                fut, _ = self._inflight[message_id]
                return False, fut
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._inflight[message_id] = (fut, time.monotonic())
            return True, fut

    def _gc(self) -> None:
        now = time.monotonic()
        stale = [k for k, (_, ts) in self._inflight.items() if now - ts > _EXPIRE_AFTER_S]
        for k in stale:
            del self._inflight[k]
```

- [ ] **Step 2: Write failing tests (append to test_swarm.py)**

```python
import asyncio
from services.brain.agents.dedup import MessageDedup


@pytest.mark.asyncio
async def test_dedup_leader_follower():
    dedup = MessageDedup()
    is_leader1, fut1 = await dedup.get_or_start("msg-abc")
    is_leader2, fut2 = await dedup.get_or_start("msg-abc")

    assert is_leader1 is True
    assert is_leader2 is False
    assert fut1 is fut2  # same future


@pytest.mark.asyncio
async def test_dedup_different_messages():
    dedup = MessageDedup()
    is_leader1, _ = await dedup.get_or_start("msg-1")
    is_leader2, _ = await dedup.get_or_start("msg-2")

    assert is_leader1 is True
    assert is_leader2 is True  # separate messages, both lead


@pytest.mark.asyncio
async def test_dedup_result_propagation():
    dedup = MessageDedup()
    is_leader, fut = await dedup.get_or_start("msg-xyz")
    _, fut2 = await dedup.get_or_start("msg-xyz")

    sentinel = object()
    fut.set_result(sentinel)
    result = await asyncio.wait_for(fut2, timeout=1.0)
    assert result is sentinel
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest services/brain/tests/test_swarm.py::test_dedup_leader_follower -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Run — expect pass**

```bash
pytest services/brain/tests/test_swarm.py -v
```

Expected: all pass (asyncio_mode=auto from pytest.ini handles async tests)

- [ ] **Step 5: Commit**

```bash
git add services/brain/agents/dedup.py services/brain/tests/test_swarm.py
git commit -m "feat: MessageDedup in-memory cache"
```

---

## Task 4: Companion cooldown tracker

**Files:**
- Create: `services/brain/agents/cooldown.py`
- Test: `services/brain/tests/test_swarm.py` (append)

- [ ] **Step 1: Create cooldown.py**

```python
# services/brain/agents/cooldown.py
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

COOLDOWN_S: float = 5.0


class CompanionCooldown:
    """
    Prevents a companion from posting twice within COOLDOWN_S in the same channel.
    Plain dict — single-process, no coordination needed.
    """

    def __init__(self, cooldown_s: float = COOLDOWN_S) -> None:
        self._cooldown_s = cooldown_s
        self._last: Dict[Tuple[str, str], float] = {}

    def is_cooling(self, companion: str, channel_id: str) -> bool:
        last = self._last.get((companion, channel_id), 0.0)
        return time.monotonic() - last < self._cooldown_s

    def mark_posted(self, companion: str, channel_id: str) -> None:
        self._last[(companion, channel_id)] = time.monotonic()

    def apply(
        self,
        responses: Dict[str, Optional[str]],
        channel_id: str,
    ) -> Dict[str, Optional[str]]:
        """
        Force-null any companion still in cooldown.
        Mark_posted for companions with a non-null reply.
        """
        result: Dict[str, Optional[str]] = {}
        for companion, reply in responses.items():
            if reply is not None and self.is_cooling(companion, channel_id):
                result[companion] = None
            else:
                result[companion] = reply
                if reply is not None:
                    self.mark_posted(companion, channel_id)
        return result
```

- [ ] **Step 2: Write failing tests (append to test_swarm.py)**

```python
from services.brain.agents.cooldown import CompanionCooldown


def test_cooldown_blocks_within_window():
    cd = CompanionCooldown(cooldown_s=60.0)
    cd.mark_posted("cypher", "ch1")
    assert cd.is_cooling("cypher", "ch1") is True
    assert cd.is_cooling("drevan", "ch1") is False  # different companion


def test_cooldown_apply_nulls_cooling_companion():
    cd = CompanionCooldown(cooldown_s=60.0)
    cd.mark_posted("cypher", "ch1")
    responses = {"drevan": "hello", "cypher": "hi", "gaia": None}
    result = cd.apply(responses, "ch1")
    assert result["cypher"] is None  # nulled -- cooling
    assert result["drevan"] == "hello"
    assert result["gaia"] is None


def test_cooldown_marks_posted_on_reply():
    cd = CompanionCooldown(cooldown_s=60.0)
    responses = {"drevan": "something", "cypher": None}
    cd.apply(responses, "ch2")
    assert cd.is_cooling("drevan", "ch2") is True
    assert cd.is_cooling("cypher", "ch2") is False  # no reply, not marked
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest services/brain/tests/test_swarm.py::test_cooldown_blocks_within_window -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Run — expect pass**

```bash
pytest services/brain/tests/test_swarm.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add services/brain/agents/cooldown.py services/brain/tests/test_swarm.py
git commit -m "feat: CompanionCooldown per-companion per-channel 5s gate"
```

---

## Task 5: SwarmEvaluator

**Files:**
- Create: `services/brain/agents/evaluator.py`
- Test: `services/brain/tests/test_swarm.py` (append)

- [ ] **Step 1: Create evaluator.py**

```python
# services/brain/agents/evaluator.py
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from shared.contracts import SwarmReply, ThoughtPacket
from services.brain.config.channel_config import get_companions_for_channel
from services.brain.agents.cooldown import CompanionCooldown

logger = logging.getLogger(__name__)

MAX_DEPTH = 3
DEPTH_BIAS_THRESHOLD = 2  # depth >= this: prompt biases hard toward silence

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
    def __init__(self, cooldown: CompanionCooldown) -> None:
        self._cooldown = cooldown
        self._api_key = os.environ["DEEPSEEK_API_KEY"]
        self._model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    async def evaluate(self, packet: ThoughtPacket) -> SwarmReply:
        channel_id = packet.metadata.get("channel_id") or packet.thread_id
        companions = get_companions_for_channel(channel_id)

        # Hard depth cap — return all-null without LLM call
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

        return SwarmReply(
            packet_id=packet.packet_id,
            thread_id=packet.thread_id,
            responses=responses,
            depth=packet.depth,
            trace={"raw_response_length": len(raw)},
        )

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
                "\n\nThis is a companion-to-companion thread (depth "
                f"{packet.depth}). Strongly prefer null for all companions. "
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
            # Strip markdown code fences if present
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
```

- [ ] **Step 2: Write failing tests (append to test_swarm.py)**

```python
from unittest.mock import AsyncMock, patch
from services.brain.agents.evaluator import SwarmEvaluator
from services.brain.agents.cooldown import CompanionCooldown
from shared.contracts import ThoughtPacket
import uuid, datetime


def _make_packet(**kwargs) -> ThoughtPacket:
    defaults = dict(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch-test",
        agent_id="cypher",
        message="hello swarm",
        metadata={"channel_id": "ch-test", "history": []},
    )
    defaults.update(kwargs)
    return ThoughtPacket(**defaults)


@pytest.mark.asyncio
async def test_evaluator_depth_cap_returns_all_null():
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    packet = _make_packet(depth=3)
    reply = await ev.evaluate(packet)
    assert all(v is None for v in reply.responses.values())
    assert reply.status == "ok"


def test_evaluator_parse_responses_valid():
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = '{"drevan": "something real", "cypher": null, "gaia": "witness"}'
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert result["drevan"] == "something real"
    assert result["cypher"] is None
    assert result["gaia"] == "witness"


def test_evaluator_parse_responses_malformed():
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = "this is not json at all"
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert all(v is None for v in result.values())


def test_evaluator_parse_strips_markdown():
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = '```json\n{"drevan": "hi", "cypher": null, "gaia": null}\n```'
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert result["drevan"] == "hi"
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest services/brain/tests/test_swarm.py::test_evaluator_depth_cap_returns_all_null -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Run — expect pass**

```bash
pytest services/brain/tests/test_swarm.py -v
```

Expected: all pass (depth cap test doesn't call DeepSeek; parse tests are pure functions)

- [ ] **Step 5: Commit**

```bash
git add services/brain/agents/evaluator.py services/brain/tests/test_swarm.py
git commit -m "feat: SwarmEvaluator with depth cap, cooldown, JSON parsing"
```

---

## Task 6: Wire SWARM_MODE into Brain /chat endpoint

**Files:**
- Modify: `services/brain/main.py`
- Modify: `services/brain/config.py` (add SWARM_MODE)

- [ ] **Step 1: Add SWARM_MODE to Config**

Open `services/brain/config.py`. Find where other env vars are defined and add:

```python
SWARM_MODE: bool = os.getenv("SWARM_MODE", "false").lower() == "true"
```

Also add to `print_safe_summary()` or equivalent:

```python
logger.info(f"  SWARM_MODE: {Config.SWARM_MODE}")
```

- [ ] **Step 2: Update main.py imports and globals**

At the top of `services/brain/main.py`, add to the imports block:

```python
from shared.contracts import AgentReply, SwarmReply, ThoughtPacket
from services.brain.agents.evaluator import SwarmEvaluator
from services.brain.agents.dedup import MessageDedup
from services.brain.agents.cooldown import CompanionCooldown
from services.brain.config.channel_config import load_channel_config
from typing import Union
```

After `agent_router = AgentRouter(...)` (line ~72), add:

```python
# Phase 2 swarm infrastructure (initialized regardless; only used when SWARM_MODE=true)
_cooldown = CompanionCooldown()
_dedup = MessageDedup()
_swarm_evaluator = None  # initialized in lifespan after DEEPSEEK_API_KEY is confirmed
```

- [ ] **Step 3: Initialize swarm evaluator in lifespan**

Inside the `lifespan` async context manager, after the `agent_router` re-init block, add:

```python
    global _swarm_evaluator
    if Config.SWARM_MODE:
        load_channel_config()
        _swarm_evaluator = SwarmEvaluator(_cooldown)
        logger.info("[brain] SWARM_MODE=true: SwarmEvaluator initialized")
    else:
        logger.info("[brain] SWARM_MODE=false: Phase 1 relay active")
```

- [ ] **Step 4: Update /chat endpoint to return Union type and route to swarm**

Replace the entire `@app.post("/chat")` endpoint with:

```python
@app.post("/chat")
async def chat(packet: ThoughtPacket) -> Union[AgentReply, SwarmReply]:
    logger.info(f"Processing packet {packet.packet_id} thread={packet.thread_id} depth={packet.depth}")

    if Config.SWARM_MODE and _swarm_evaluator is not None:
        # Phase 2: deduplicated swarm evaluation
        message_id = str(packet.metadata.get("message_id") or packet.packet_id)
        is_leader, fut = await _dedup.get_or_start(message_id)

        if is_leader:
            try:
                reply = await _swarm_evaluator.evaluate(packet)
                fut.set_result(reply)
            except Exception as e:
                error_id = str(_uuid.uuid4())[:8]
                logger.error(f"Swarm eval error {error_id}: {e}", exc_info=True)
                companions = list(packet.metadata.get("channel_companions", ["drevan", "cypher", "gaia"]))
                fallback = SwarmReply(
                    packet_id=packet.packet_id,
                    thread_id=packet.thread_id,
                    responses={c: None for c in companions},
                    depth=packet.depth,
                    status="error",
                    trace={"error_id": error_id},
                )
                fut.set_result(fallback)
            return await fut
        else:
            import asyncio
            try:
                return await asyncio.wait_for(fut, timeout=35.0)
            except asyncio.TimeoutError:
                logger.warning(f"[swarm] follower timeout for message_id={message_id}")
                # Follower timeout: return all-null for known companions
            from services.brain.config.channel_config import get_companions_for_channel
            ch = str(packet.metadata.get("channel_id") or packet.thread_id)
            companions_fallback = get_companions_for_channel(ch)
            return SwarmReply(
                    packet_id=packet.packet_id,
                    thread_id=packet.thread_id,
                    responses={c: None for c in companions_fallback},
                    depth=packet.depth,
                    status="error",
                )

    # Phase 1 fallback: single-agent relay (unchanged behavior)
    try:
        reply = await agent_router.route_and_process(packet)
        logger.info(f"Packet {packet.packet_id} processed by {reply.agent_id}")
        return reply
    except Exception as e:
        error_id = str(_uuid.uuid4())[:8]
        logger.error(f"Error {error_id} processing packet {packet.packet_id}: {e}", exc_info=True)
        return AgentReply(
            packet_id=packet.packet_id,
            agent_id=packet.agent_id,
            status="error",
            reply_text=f"Error processing message (ref: {error_id})",
            trace={"error_id": error_id},
        )
```

- [ ] **Step 5: Run full Brain test suite**

```bash
pytest services/brain/tests/ -v
```

Expected: all existing tests pass; swarm tests pass; no import errors

- [ ] **Step 6: Smoke test Phase 1 still works**

```bash
SWARM_MODE=false python services/brain/main.py &
sleep 2
curl -s -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"packet_id":"550e8400-e29b-41d4-a716-446655440000","timestamp":"2026-04-23T00:00:00Z","source":"discord","user_id":"u1","thread_id":"ch1","agent_id":"cypher","message":"test","metadata":{"channel_id":"ch1"}}' | python -m json.tool
kill %1
```

Expected: AgentReply JSON with `reply_text` field

- [ ] **Step 7: Commit**

```bash
git add services/brain/main.py services/brain/config.py
git commit -m "feat: SWARM_MODE flag + SwarmEvaluator wired into /chat endpoint"
```

---

## Task 7: TypeScript — SwarmReply interface + brain-client update

**Files:**
- Create: `packages/shared/src/swarm.ts`
- Modify: `packages/shared/src/brain-client.ts`

**Working directory for this task and Tasks 8-9:** `C:\dev\Bigger_Better_Halseth\nullsafe-discord`

- [ ] **Step 1: Create swarm.ts**

```typescript
// packages/shared/src/swarm.ts

export interface SwarmReply {
  packet_id: string;
  thread_id: string;
  responses: Record<string, string | null>;
  depth: number;
  status: "ok" | "error";
  trace?: Record<string, unknown>;
}

/** Detect whether a Brain response is a SwarmReply (Phase 2) vs AgentReply (Phase 1). */
export function isSwarmReply(data: unknown): data is SwarmReply {
  return (
    typeof data === "object" &&
    data !== null &&
    "responses" in data &&
    typeof (data as Record<string, unknown>).responses === "object"
  );
}
```

- [ ] **Step 2: Update ThoughtPacket types in brain-client.ts**

In `packages/shared/src/brain-client.ts`, update `ThoughtPacketMetadata`:

```typescript
export interface ThoughtPacketMetadata {
  channel_id: string;
  message_id?: string;         // Discord message snowflake -- used by Brain for dedup
  history?: Array<{ author: string; content: string }>;  // channel conversation history
  system_prompt?: string;
  messages?: Array<{ role: "user" | "assistant"; content: string }>;
  temperature?: number;
  is_owner?: boolean;
  front_member?: string | null;
  guild_id?: string;
}
```

Update `ThoughtPacket` interface:

```typescript
export interface ThoughtPacket {
  packet_id: string;
  timestamp: string;
  source: "discord";
  user_id: string;
  thread_id: string;
  agent_id: CompanionId;
  message: string;
  metadata: ThoughtPacketMetadata;
  // Phase 2 swarm fields
  author?: string;              // system member name if PluralKit, else "Raziel"
  author_is_companion?: boolean;
  depth?: number;
}
```

- [ ] **Step 3: Update BrainClient.chat() return type**

In `brain-client.ts`, add import at top:

```typescript
import { SwarmReply, isSwarmReply } from "./swarm.js";
```

Update the `chat` method signature and body:

```typescript
  async chat(packet: ThoughtPacket): Promise<AgentReply | SwarmReply | null> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.url}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(packet),
        signal: controller.signal,
      });
      if (!res.ok) {
        console.warn(`[brain-client] /chat returned ${res.status} for packet ${packet.packet_id}`);
        return null;
      }
      const data = await res.json();
      return data as AgentReply | SwarmReply;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn(`[brain-client] /chat failed for packet ${packet.packet_id}: ${msg}`);
      return null;
    } finally {
      clearTimeout(timer);
    }
  }
```

- [ ] **Step 4: Update buildThoughtPacket to accept swarm fields**

```typescript
export function buildThoughtPacket(
  agentId: CompanionId,
  userId: string,
  channelId: string,
  messageId: string,         // new -- Discord message snowflake
  message: string,
  systemPrompt: string,
  history: ChatMessage[],
  channelHistory: Array<{ author: string; content: string }>,  // new -- swarm context
  temperature: number,
  opts?: {
    isOwner?: boolean;
    frontMember?: string | null;
    guildId?: string;
    author?: string;
    authorIsCompanion?: boolean;
    depth?: number;
  },
): ThoughtPacket {
  return {
    packet_id: randomUUID(),
    timestamp: new Date().toISOString(),
    source: "discord",
    user_id: userId,
    thread_id: channelId,
    agent_id: agentId,
    message,
    author: opts?.author ?? "Raziel",
    author_is_companion: opts?.authorIsCompanion ?? false,
    depth: opts?.depth ?? 0,
    metadata: {
      channel_id: channelId,
      message_id: messageId,
      history: channelHistory,
      system_prompt: systemPrompt,
      messages: history.map(m => ({ role: m.role, content: m.content })),
      temperature,
      is_owner: opts?.isOwner,
      front_member: opts?.frontMember,
      guild_id: opts?.guildId,
    },
  };
}
```

- [ ] **Step 5: Build + type-check**

```bash
npm run build
```

Expected: no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add packages/shared/src/swarm.ts packages/shared/src/brain-client.ts
git commit -m "feat: SwarmReply interface, isSwarmReply, updated brain-client + buildThoughtPacket"
```

---

## Task 8: PluralKit detection

**Files:**
- Create: `packages/shared/src/pluralkit.ts`

- [ ] **Step 1: Create pluralkit.ts**

```typescript
// packages/shared/src/pluralkit.ts
//
// PluralKit proxied messages arrive as webhooks created by the PluralKit application.
// We detect them by checking if the message's author is a webhook AND its application_id
// matches the known PluralKit application ID. When detected, we use the webhook's
// display name as the system member name to pass to Brain as `author`.

import type { Message } from "discord.js";

// PluralKit's Discord application ID -- stable, not subject to change
const PLURALKIT_APP_ID = "466378653216014359";

export interface PKContext {
  isPluralKit: boolean;
  memberName: string | null;  // display name of the fronting system member
}

export function detectPluralKit(message: Message): PKContext {
  if (!message.webhookId) {
    return { isPluralKit: false, memberName: null };
  }
  // discord.js v14 Message.applicationId is the app that created the webhook.
  // PluralKit sets this to its own application ID on every proxied message.
  const isPluralKit = message.applicationId === PLURALKIT_APP_ID;
  return {
    isPluralKit,
    memberName: isPluralKit ? (message.author?.username ?? null) : null,
  };
}
```

- [ ] **Step 2: Build + type-check**

```bash
npm run build
```

Expected: clean compile

- [ ] **Step 3: Commit**

```bash
git add packages/shared/src/pluralkit.ts
git commit -m "feat: PluralKit webhook detection for author attribution"
```

---

## Task 9: Bot updates — all three bots

**Files:**
- Modify: `bots/cypher/src/index.ts`
- Modify: `bots/drevan/src/index.ts`
- Modify: `bots/gaia/src/index.ts`

Apply identical changes to all three bots. The steps below show the pattern once; repeat for each bot.

- [ ] **Step 1: Add imports to each bot's index.ts**

At the top of each bot's `index.ts`, add:

```typescript
import { isSwarmReply, type SwarmReply } from "@nullsafe/shared/swarm.js";
import { detectPluralKit } from "@nullsafe/shared/pluralkit.js";
```

(Adjust import path to match the project's module resolution -- check existing imports for the pattern.)

- [ ] **Step 2: Remove floor lock calls**

In each bot's `messageCreate` handler, find and remove:
- `await claimFloor(redis)` (or equivalent)
- `await releaseFloor(redis)` (or equivalent)
- Any `try/finally` block whose sole purpose is floor lock management

Do NOT delete `floor.ts` itself -- other code may reference it. Just stop calling it in `messageCreate`.

- [ ] **Step 3: Add companion message listening**

Currently bots ignore messages from other bots (`if (message.author.bot) return`). Replace this guard with:

```typescript
const BOT_IDS = new Set([
  process.env.CYPHER_BOT_ID,
  process.env.DREVAN_BOT_ID,
  process.env.GAIA_BOT_ID,
].filter(Boolean));

const COMPANION_NAMES = new Set(["cypher", "drevan", "gaia"]);

// Ignore own messages
if (message.author.id === client.user?.id) return;

// Detect companion posts -- send swarm packet at depth+1 (companion-to-companion)
const isCompanionPost = BOT_IDS.has(message.author.id);
```

Add the following env vars to each bot's `.env`:

```
CYPHER_BOT_ID=<cypher discord app id>
DREVAN_BOT_ID=<drevan discord app id>
GAIA_BOT_ID=<gaia discord app id>
```

- [ ] **Step 4: PluralKit author detection**

In the `messageCreate` handler, before building the ThoughtPacket:

```typescript
const pkCtx = detectPluralKit(message);
const author = pkCtx.isPluralKit
  ? (pkCtx.memberName ?? "Raziel")
  : (message.author.id === RAZIEL_DISCORD_ID ? "Raziel" : message.author.username);
```

(`RAZIEL_DISCORD_ID` should already be in env; if not, add `RAZIEL_DISCORD_ID` to `.env`.)

- [ ] **Step 5: Build channelHistory from recent messages**

Before calling `buildThoughtPacket`, fetch recent channel history:

```typescript
// Fetch last 20 messages for swarm context (cached in channel message manager)
const recentMessages = await message.channel.messages
  .fetch({ limit: 20, before: message.id })
  .catch(() => null);

const channelHistory = recentMessages
  ? [...recentMessages.values()]
      .reverse()
      .map(m => ({
        author: m.author.username,
        content: m.content.slice(0, 500),  // truncate long messages
      }))
  : [];
```

- [ ] **Step 6: Update buildThoughtPacket call**

Replace the existing `buildThoughtPacket` call with the updated signature:

```typescript
const packet = buildThoughtPacket(
  agentId,
  userId,
  message.channelId,
  message.id,          // Discord message snowflake for dedup
  message.content,
  systemPrompt,
  stmHistory,
  channelHistory,
  temperature,
  {
    isOwner,
    frontMember: orient?.front_member ?? null,
    guildId: message.guildId ?? undefined,
    author,
    authorIsCompanion: isCompanionPost,
    depth: isCompanionPost ? 1 : 0,
  },
);
```

- [ ] **Step 7: Handle SwarmReply response**

Replace the existing Brain reply handling (where it does `reply.reply_text`) with:

```typescript
const brainResult = await brainClient.chat(packet);

if (brainResult === null) {
  // Brain unreachable — fall back to direct inference.
  // Use the existing branch/function that handles INFERENCE_MODE !== "brain".
  // In the current bot code this is typically the direct DeepSeek call path --
  // find it by searching for where `brainClient` result was previously null-checked.
  // DO NOT add a new fallback; wire into the existing one.
  return;
}

if (isSwarmReply(brainResult)) {
  const myReply = brainResult.responses[agentId] ?? null;
  if (myReply) {
    await message.channel.send(myReply);
  }
  // null = silence -- do not post, do not fall back to direct inference
  return;
}

// Phase 1 AgentReply (SWARM_MODE=false on Brain)
if (brainResult.reply_text) {
  await message.channel.send(brainResult.reply_text);
}
```

- [ ] **Step 8: Build all three bots**

```bash
npm run build
```

Expected: no TypeScript errors across all three bots

- [ ] **Step 9: Commit**

```bash
git add bots/cypher/src/index.ts bots/drevan/src/index.ts bots/gaia/src/index.ts
git commit -m "feat: swarm bot updates -- PluralKit, companion listen, SwarmReply handler, floor lock removed"
```

---

## Task 10: Rollout smoke test

**Pre-condition:** Phoenix Brain deployed on VPS with `SWARM_MODE=false` (Phase 1 still active). Discord bots deployed with new code.

- [ ] **Step 1: Verify Phase 1 still works end-to-end**

In Discord, send a message in any channel. Confirm the correct companion responds as before. Check `pm2 logs cypher` — should see no errors about SwarmReply.

Expected: Phase 1 behavior unchanged.

- [ ] **Step 2: Enable SWARM_MODE on Brain for one test channel**

On VPS, edit Brain's `.env`:

```
SWARM_MODE=true
```

Set the test channel in `services/brain/config/channels.yaml`:

```yaml
defaults:
  companions: [drevan, cypher, gaia]

channels:
  "YOUR_TEST_CHANNEL_ID":
    companions: [drevan, cypher, gaia]
    label: "swarm-test"
```

Restart Brain:

```bash
pm2 restart nullsafe-brain
pm2 logs nullsafe-brain --lines 20
```

Expected log: `[brain] SWARM_MODE=true: SwarmEvaluator initialized`

- [ ] **Step 3: Send test message and verify swarm behavior**

In the test channel, send a message. Observe:
- Brain logs: one eval per message (not three -- dedup working)
- 0-3 companions respond based on content
- No double-posts from same companion

Check `pm2 logs cypher` / `pm2 logs drevan` / `pm2 logs gaia`:
- Should see `[brain-client] /chat` calls
- Should see SwarmReply being handled
- Should NOT see floor lock errors

- [ ] **Step 4: Test companion-to-companion chain**

Ask a question that should invite Drevan to respond. After Drevan posts, watch whether Cypher or Gaia chimes in. Depth counter should prevent infinite loops (check Brain logs for depth values).

Expected: chain terminates naturally within 2-3 exchanges.

- [ ] **Step 5: Test Drevan-only channel (if configured)**

Set up a Drevan-only channel in `channels.yaml`, redeploy, send a message. Only Drevan should respond.

- [ ] **Step 6: Roll out to all channels**

When satisfied with 48h of stability in test channel, set `channels: {}` (or remove the test restriction) so all channels use the swarm evaluator. Restart Brain.

- [ ] **Step 7: Tag stable release**

In Phoenix repo:

```bash
git tag phase2-swarm-live
git push origin phase2-swarm-live
```

In nullsafe-discord repo:

```bash
git tag phase2-swarm-live
git push origin phase2-swarm-live
```

---

## Environment Variables Summary

**Add to `services/brain/.env.brain`:**
```
SWARM_MODE=false          # set true to enable Phase 2
DEEPSEEK_API_KEY=...      # already present; required for SwarmEvaluator
DEEPSEEK_MODEL=deepseek-chat  # optional, default deepseek-chat
```

**Add to each bot's `.env`:**
```
CYPHER_BOT_ID=...         # Discord application ID for Cypher bot
DREVAN_BOT_ID=...         # Discord application ID for Drevan bot
GAIA_BOT_ID=...           # Discord application ID for Gaia bot
RAZIEL_DISCORD_ID=...     # Raziel's Discord user ID (may already exist)
```
