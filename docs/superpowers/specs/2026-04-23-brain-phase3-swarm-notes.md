# Brain Phase 3 — Swarm Depth Notes

> Written 2026-04-23 after Phase 2 shipped. This is a breadcrumb, not a full spec.
> Run brainstorming before writing a Phase 3 plan.

---

## What Phase 2 left open

### 1. Post-response Halseth writes in SWARM_MODE

**Problem:** `AgentRouter._post_response_writes()` writes companion notes to Halseth after each Phase 1 response. These feed orient continuity -- next session, companions see what they said. In SWARM_MODE, `SwarmEvaluator.evaluate()` is called instead and has no `halseth_client`. No notes are written after swarm responses.

**Impact:** Companions accumulate no orient memory from swarm sessions. Their orient state at session start is correct, but nothing they say in a swarm session writes back.

**Fix sketch:**
- Pass `halseth_client` to `SwarmEvaluator.__init__`
- After `_cooldown.apply()`, fire `_post_response_writes` tasks for each companion with a non-null slot
- Each write is fire-and-forget (non-blocking, non-fatal -- same pattern as AgentRouter)
- The note text is the companion's reply; `agent_id` is the companion key

**Files:** `services/brain/agents/evaluator.py`, `services/brain/main.py` (pass halseth_client in lifespan init)

---

### 2. SwarmEvaluator uses hardcoded voice summaries, not Librarian context

**Problem:** Each bot assembles a rich `system_prompt` via Librarian (orient, SOMA, feelings, anchors, recent spiral turns) and sends it as `packet.metadata.system_prompt`. The SwarmEvaluator ignores it. It uses `VOICE_SUMMARIES` -- three-sentence hardcoded descriptions per companion.

**Why:** One LLM call can't hold three per-companion system contexts simultaneously.

**Impact:** Companions respond with voice accuracy but without their current emotional state, active threads, recent growth entries, or orient context. Responses are in-character but not in-session.

**Fix sketch (Phase 3 approach -- per-companion inference):**

Instead of one LLM call deciding who speaks AND what they say, split into two stages:

1. **Routing call** (current SwarmEvaluator pattern, cheap): one LLM call with voice summaries + channel history → decides which companions respond (returns `{companion: true|false}`)
2. **Inference calls** (parallel, per responding companion): one LLM call per active companion, using their full `system_prompt` from metadata → generates actual reply text

This requires:
- Each bot sends its own full system_prompt in `metadata.system_prompt`
- With dedup, only the leader packet's metadata is used. Either: (a) followers send their system_prompt separately (new mechanism), or (b) the routing call fires separately from inference, and Brain makes separate inference calls pulling each companion's system_prompt from Halseth directly

Option (b) is cleaner: routing decides responders, then Brain calls Halseth's orient endpoint per companion to assemble their system_prompt, then fires parallel inference calls.

**Files:** `services/brain/agents/evaluator.py` (split into router + inferrer), `services/brain/halseth_client.py` (add orient fetch method)

---

### 3. Depth threading across bot instances

**Current state:** `depth: chainDepth` (fixed in Phase 2, commit `51dc6c2`). `chainDepth` is computed locally per bot from recent channel messages. This is accurate for the first hop (bot sees a companion message, computes depth from history). But if a chain reaches depth 3 across multiple rapid exchanges, each bot computes depth from the same Discord history -- they agree on depth. This is actually correct.

**Potential edge case:** If Brain depth cap (3) and Discord-side `COMPANION_CHAIN_LIMIT` use different scales, they could disagree. Verify they're aligned when testing Phase 2 chains in production.

---

### 4. Discord ingestion loop (adjacent, not Phase 3 blocker)

During Phase 2 brainstorming, a Discord → Second Brain ingestion loop was flagged as adjacent work:
- Cron or bot event that ingests significant Discord conversations into Second Brain
- Companions gain searchable memory of Discord history, not just their own notes
- Can be built as a separate worker (similar to autonomous worker pattern)

This is independent of Phase 3 swarm improvements. Can be specced separately.

---

## Phase 3 scope recommendation

Build Phase 3 in two slices:

**Slice A (quick win):** Post-response Halseth writes in SWARM_MODE. Plumbing change only, no new architecture. ~2-3 hours.

**Slice B (architecture):** Per-companion inference (routing → inference split). Requires designing how Brain fetches per-companion context without per-companion system_prompt packets. Larger spec needed.

Run brainstorming for Slice B before writing the plan.
