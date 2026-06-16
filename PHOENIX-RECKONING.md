# Phoenix Reckoning (2026-06-16)

This document replaces the old "Phoenix absorbs BBH" story. It is the authoritative
statement of what Phoenix is, what it is not, and what work on it still makes sense.

Written when school let out and the long-deferred "summer 2026 Phoenix Heart Phase"
arrived. We looked at what we actually have instead of what the plan assumed, and the
plan was wrong.

---

## The inversion

The original plan: Phoenix is a reliability-first Python/FastAPI rewrite (Relay buffers an
offline workstation Brain; a WebMind microservice replaces Halseth; Python bots replace the
TypeScript bots). Phoenix is the destination; BBH is the lean prototype it will absorb.

What actually happened: **BBH overtook Phoenix and became the mind.** Halseth (Cloudflare
Worker + D1, migration 0083+) grew orient, ground, threads, SOMA, growth, autonomy, guardian,
council, club, creatures, drives, tools, heat/decay, EmotionalRAG, identity kernel, and more.
The TypeScript bots grew a six-provider inference stack with fallback. Hearth, second-brain,
and plural are all live and mature.

Meanwhile, of Phoenix's five specced services:
- **Relay, Web UI, Python discord_bot**: already archived in a prior session (the docs never caught up).
- **WebMind microservice**: a dormant scaffold roughly 80 migrations behind Halseth (no semantic
  search, SQLite). Archived 2026-06-16.
- **Brain**: live, but optional. The bots route to it (`BrainClient` -> `/chat`) and fall back to
  direct inference without it. Its own `webmind_client.py` points at the **Halseth** URL. In live
  code, Brain already treats Halseth as the WebMind.

"Phoenix absorbs BBH" was backwards. The reliability kernel solved a problem we no longer have
(an offline workstation Brain; Brain now runs always-on on the VPS, and the bots carry their own
fallback). Keeping the story alive had a cost: every cross-project review dragged a dead cathedral,
and "park it for Phoenix" became a way to defer decisions to a host that was never going to arrive
in its specced form.

---

## What Phoenix is now

**Phoenix is the VPS stateful-runtime tier of BBH.** It is the home for the things Cloudflare
Workers genuinely cannot do: persistent processes, background work, local-model orchestration, and
event-driven autonomy.

- **Halseth stays the mind.** The WebMind-replaces-Halseth plan is dead.
- **Brain** is Phoenix's one live organ: inference orchestration and the swarm evaluator, reachable
  at `/chat`, backed by Halseth for continuity.
- The other stateful work that already lives on the VPS (the autonomous worker, voice, the LM Studio
  local rung) belongs to this tier conceptually, even though it currently ships from `nullsafe-discord`.

What Phoenix is **not**: a rewrite of Halseth, a replacement for the TypeScript bots, or a separate
durability kernel. Those are archived under `_archive/`.

---

## June roadmap: the deferred backlog, re-triaged against reality

Every item that was "parked for Phoenix" is decided here. Three buckets.

### DO (still makes sense)
- **Event-driven autonomy (polling -> events).** The flagship Phoenix-tier win. The autonomous worker
  and crons poll D1 on a timer; a persistent VPS process can wake on signals (Redis pub/sub or a
  lightweight event bus) instead. This is exactly what a stateful runtime tier is for. Highest priority.
- **Brain swarm mid-inference tool-loop.** Brain is the live organ on the VPS; the tool exec core and
  endpoints already exist. Letting Brain call tools mid-inference is a genuine runtime-tier capability.
- **Error-masking -> contextual logging standard (BBH-wide).** Real operational value given this suite's
  history of silent failures. Adopt "log caught errors with context" as a convention; apply to the
  highest-value silent sites first. This is BBH hygiene, not Phoenix-gated.
- **Monolith decomposition (bot-message-handler ~900L, execBotOrient ~1000L).** Real BBH tech debt.
  Do it incrementally on its own merits when touching those paths; not urgent, not Phoenix-gated.

### DROP (already built past)
- **Slice 7 (MCP Adapter surface).** Halseth already exposes MCP (`POST /mcp`) and Librarian is the
  companion entry point. The adapter was for the dead WebMind microservice. Dropped.
- **Hearth PhoenixTabs "Runs/Seeds" tabs.** They were placeholders for the Phoenix WebMind, now archived.
  Autonomy runs/seeds are already surfaced at `/autonomous` and `/companions/[id]/autonomy`. Dead tabs removed.
- **WebMind microservice / Heart Phase as specced.** Archived. Halseth won.

### PARK on merits (not "for Phoenix"; genuine open design questions)
- **Emergent-SOMA rework (inspo take 11).** Risky; needs a design pass. A BBH item, parked on merits.
- **Experiment loop (inspo take 12).** Needs a trusted metric before it is safe to close a loop on. BBH item.
- **Coworker integration.** No defined path; external dependency. Parked.
- **D1 `batch()` atomicity.** Non-issue (resolved in `SWEEP_REPORT.md` #7): `batch()` is atomic for pure
  writes; the memory note concerns read-modify-write, which the live call sites do not do.

---

## What lives where now

| Path | Status |
|------|--------|
| `services/brain/` | LIVE. Inference orchestration + swarm. pm2 `nullsafe-brain` on the VPS. |
| `shared/` | LIVE. Pydantic contracts Brain depends on. |
| `_archive/services/{relay,web_ui,discord_bot,webmind}/` | Archived. The specced 5-service rewrite. |
| `_archive/integration_tests/` | Archived. Tested the old multi-service topology. |
| `_archive/docs/{PHOENIX_HEART_PHASE_PLAN,WEBMIND_V0_DECISION,WEBMIND_V0_SCHEMA_SKETCH}.md` | Archived plans for the dead rewrite. |

The live mind is BBH. See `../Bigger_Better_Halseth/CLAUDE.md`.
