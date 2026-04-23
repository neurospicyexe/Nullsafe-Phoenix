# Brain Phase 2 — Heterarchic Swarm Design

**Date:** 2026-04-22
**Scope:** Nullsafe Phoenix Brain + nullsafe-discord bots
**Status:** Approved for implementation

---

## Problem

Brain Phase 1 relays whoever calls it. Each bot sends a ThoughtPacket with its own `agent_id`; Brain routes back to that same bot. The result is three independent bots that happen to share memory -- not a swarm. Companions can't chime in naturally, can't respond to each other, and the floor lock enforces an artificial turn-taking model that's architecturally wrong for heterarchy.

The goal: companions speak when they have something genuine to contribute. Not when tagged. Not in turns. Like any group conversation where someone chimes in because the moment calls for it.

---

## Architecture

### SwarmEvaluator replaces AgentRouter

One LLM call per incoming message. Brain receives a ThoughtPacket, looks up which companions are active in that channel, and calls the SwarmEvaluator with the full context. The evaluator returns a structured response for every active companion -- either their reply or null (silence). Each bot independently checks the SwarmReply for its own name and posts if non-null.

No floor lock. No turn-taking. Silence is a valid and often correct output.

### SwarmEvaluator prompt structure

```
System: You are coordinating responses for a companion swarm. Each companion has a distinct voice and role. Not all companions need to respond to every message. Silence is often more honest than a forced reply.

Context:
- Channel: {channel_label}
- Active companions: {channel_companions}
- Author: {author}  # system member name if PluralKit-proxied, else "Raziel"
- Conversation history (last N messages): {history}
- Companion orient data: {orient_blocks}  # SOMA state + recent memories per companion
- Relevant memories (Phase 3): {memory_block}  # RAG from Second Brain -- empty until Phase 3

For each active companion, write their response if they have something genuine to contribute,
or null if silence is more honest. Companions respond in their own voice.
Format: JSON object {"drevan": "...", "cypher": null, "gaia": "..."}
```

### Channel config

Static YAML in `brain/config/channels.yaml`. Brain loads at startup. Bots carry the same config and populate `channel_companions` before sending ThoughtPacket.

```yaml
defaults:
  companions: [drevan, cypher, gaia]

channels:
  "DREVAN_ONLY_CHANNEL_ID":
    companions: [drevan]
    label: "drevan-intimate"

  "FUTURE_EXTERNAL_GROUP_ID":
    companions: [cypher]
    label: "external-cypher-only"
```

New channel entries require a config deploy, not a migration. Intentional -- channel topology is a deliberate architectural decision, not runtime state.

---

## Contracts

### ThoughtPacket (updated)

```python
class ThoughtPacket(BaseModel):
    agent_id: Literal["drevan", "cypher", "gaia"]  # which bot sent it
    message_id: str    # Discord message ID -- used by Brain for dedup
    channel_id: str    # Brain resolves active companions from channel config server-side
    author: str        # "Raziel" or system member name (PluralKit-aware)
    author_is_companion: bool  # True when another companion triggered this
    content: str
    thread_id: str
    depth: int = 0     # companion-to-companion chain depth
    history: list[dict]  # last N messages [{author, content, timestamp}]
```

`channel_companions` is removed from the packet. Brain owns channel config; bots send `channel_id` and Brain resolves which companions are active. Single source of truth.

### SwarmReply (new, replaces AgentReply)

```python
class SwarmReply(BaseModel):
    responses: dict[str, str | None]  # {"drevan": "...", "cypher": None, "gaia": "..."}
    depth: int
    thread_id: str
```

### AgentReply (deprecated)

Kept during transition for any code still referencing it. Removed once all bots updated.

### Dedup: one eval per message, three bots all receive the result

All three active bots send ThoughtPackets when a message arrives. Brain deduplicates by `message_id`: the first packet starts evaluation; subsequent packets for the same `message_id` (within a 2s window) wait and receive the cached SwarmReply. All three bots get the same reply; each posts its own slot independently. No Redis pub/sub needed -- each bot gets its reply via its own HTTP response, just from the same cached evaluation.

This costs one LLM call per user message regardless of how many bots are active.

---

## Anti-Loop

Three guards, all lightweight and in-process (no Redis, no D1):

**1. Companion-origin dampening**
When `author_is_companion = True`, the evaluator prompt adds: "Another companion just spoke. Only respond if you have something that genuinely adds -- silence is usually correct here." Probabilistic, not a hard block. Guides the LLM toward null.

**2. Depth counter**
- `depth 0`: normal evaluation
- `depth 1`: companion replied to companion once -- mild dampening
- `depth >= 2`: evaluator prompt shifts to "respond only if thread is genuinely unresolved"
- `depth >= 3`: Brain returns all-null without calling LLM

Depth is set by Brain, not by bots. When a bot's post triggers a new ThoughtPacket (companion posting → other bots see it → send ThoughtPacket), Brain increments depth from the incoming packet's depth field.

**3. Per-companion cooldown (5s per channel)**
Brain maintains `last_post: dict[companion][channel_id] = timestamp` in memory. If a companion posted within 5s in that channel, their slot is forced null regardless of LLM output. Plain Python dict -- ephemeral, single-process, no coordination needed.

**Expected LLM call budget per user message:**
- User message → 1 eval (deduped) → up to 3 companion responses
- Each companion response → 1 eval (deduped) at depth+1
- Worst case: user message triggers 2 companion replies → 2 more evals at depth=1 → depth=2 dampening kicks in, typically yields 0-1 more responses → 1 more eval max
- Practical ceiling: ~4 LLM calls per user message in an active multi-companion thread. Normal single exchanges: 1-2 calls.

---

## Bot-Side Changes

**Remove floor lock.** The Redis mutex in `packages/shared` is removed. Each bot listens to all messages in channels where it's active, sends ThoughtPacket, posts if SwarmReply contains its name.

**PluralKit handling.** Bots detect PluralKit webhook messages (webhook created by PluralKit application ID, display name matches system member). When detected: `author = system_member_name`, `author_is_companion = False`. This ensures Brain/companions know who in the system is fronting and calibrate register accordingly. Configured via `.env`: `PLURALKIT_APP_ID`, `RAZIEL_DISCORD_ID`.

**Bot listens to companion messages.** Bots currently ignore other bots. Phase 2 requires each bot to observe companion posts in shared channels so Brain can evaluate chime-in opportunities. Bots send ThoughtPacket when they see another companion post, with `author_is_companion = True` and `depth = prior_depth + 1`.

**BrainClient updated.** Return type changes from `AgentReply` to `SwarmReply`. Each bot checks `reply.responses[this.agentId]`.

---

## Context and Memory

### Phase 2 (this spec)
- Conversation history: last 20 messages from channel, passed in ThoughtPacket
- Orient data: each companion's boot orient (SOMA state, recent notes, handover summary) fetched from Halseth at evaluation time
- Result: richer evaluator context than current single-relay routing

### Phase 3 (adjacent, not this spec)
- SecondBrainClient: Brain queries Second Brain semantically at inference time
- Relevant memories injected into `memory_block` in evaluator prompt
- "You mentioned X three weeks ago" becomes possible in Discord
- Phase 2 is designed with the `memory_block` slot already in the prompt -- Phase 3 fills it in

---

## Discord Ingestion Loop (adjacent parallel work)

**Gap:** Discord conversations don't feed Second Brain. Claude.ai companions boot without knowing what happened in Discord. The swarm isn't fully omnidirectional.

**Fix:** Bots write conversation summaries to Halseth after each exchange (new endpoint or companion_journal source). Second Brain puller picks them up as a new source type (`discord_conversation`). Claude.ai companions get Discord history at orient. SwarmEvaluator can eventually pull deeper history from Second Brain rather than Discord's in-memory cache.

This is a clean pipeline addition (new puller + new write path in bots). Should be built alongside or immediately after Phase 2 -- not after Phase 3.

---

## Per-Companion Workers (flagged, not in scope)

One autonomous worker currently runs the growth pipeline for all three companions. Per-companion workers would give each companion their own exploration cadence, seed priorities, and reflection types. The schema already supports this (`autonomy_seeds.companion_id`). Worth a future brainstorm -- not Phase 2.

---

## Files Affected

**Nullsafe Phoenix:**
- `shared/contracts.py` -- ThoughtPacket + SwarmReply
- `services/brain/agents/router.py` -- replace AgentRouter with SwarmEvaluator
- `services/brain/agents/evaluator.py` -- new file, SwarmEvaluator logic
- `services/brain/config/channels.yaml` -- new file, channel config
- `services/brain/main.py` -- wire SwarmEvaluator, load channel config

**nullsafe-discord:**
- `packages/shared/src/brain-client.ts` -- SwarmReply return type
- `packages/shared/src/floor-lock.ts` -- remove or stub (no longer used)
- `bots/cypher/src/index.ts` -- listen to companion messages, PluralKit detection, SwarmReply handling
- `bots/drevan/src/index.ts` -- same
- `bots/gaia/src/index.ts` -- same
- `packages/shared/src/channel-config.ts` -- new file, reads channels.yaml, populates channel_companions

---

## Failure Modes

Brain timeout (>10s): bot receives no reply, silent drop -- no post. Not retried.
SwarmReply JSON malformed: Brain logs error, returns all-null SwarmReply. Bot posts nothing.
LLM refuses or returns empty: Brain returns all-null SwarmReply. Bot posts nothing.
Brain unreachable: bot falls back to Phase 1 behavior (routes to its own `agent_id` via legacy AgentReply). Phase 1 fallback is removed only after Phase 2 is stable in prod.

Failure is always silent-drop. Companions do not post error messages into Discord.

---

## Rollout

Phase 1 is live. Bots currently expect `AgentReply` from Brain.

1. Deploy updated Brain with SwarmEvaluator behind a feature flag (`SWARM_MODE=false` default)
2. Update all three bots to handle both `AgentReply` (Phase 1) and `SwarmReply` (Phase 2) -- detect by response shape
3. Enable `SWARM_MODE=true` in Brain env for one test channel first
4. Verify: correct companions respond, depth counter works, dedup fires correctly, no double-posts
5. Roll out to all channels; remove Phase 1 fallback code once stable for 48h

No database migrations required. No Halseth changes required. Brain + bots only.

---

## What This Is Not

- Not a hierarchy. No companion leads. No routing by personality type.
- Not a voting system. The LLM decides based on context, not rules.
- Not a chatbot round-robin. Silence is first-class.
- Not finished until Discord ingestion loop closes the Claude.ai gap.
