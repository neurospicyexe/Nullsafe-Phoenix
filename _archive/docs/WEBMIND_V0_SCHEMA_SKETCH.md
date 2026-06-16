# WebMind v0 Schema + Contract Sketch (Slice 1)

Created: February 24, 2026
Status: **SUPERSEDED** -- Schema was implemented in Halseth (wm_* tables), not here.
Live schema: `halseth/migrations/0027_webmind_v0.sql` onward through migration 0044.
Keep as Heart Phase reference for when Phoenix implements its own WebMind layer.

## Purpose

This document defines the initial vocabulary, data records, and endpoint/tool sketches for WebMind v0 (continuity + handoffs + threads).

It is intentionally small and deterministic.

## Scope (v0)

In scope:

- continuity retrieval (`mind_orient`, `mind_ground`)
- session handoffs (read/write)
- active threads (list/upsert)
- companion continuity notes (simple append-only)

Out of scope:

- tasks/reminders
- bond state
- autonomous schedules
- semantic embeddings

## Domain Vocabulary (Locked for v0)

### Identity Anchor

Stable companion-facing grounding material that helps recover continuity after context loss.

Examples:

- name / role summary
- anchor phrases
- constraints summary
- current identity version hash (from Brain identity loader)

### Continuity Snapshot

A synthesized read model for session recovery that combines:

- identity anchor summary
- active threads
- latest handoff
- recent notes

This is a **read model**, not a primary write table.

### Session Handoff

A structured end-of-session or checkpoint record describing:

- what happened
- what matters next
- what is unresolved
- what tone/state to carry forward

### Mind Thread

A persistent topic/commitment/intention for a companion, scoped by `agent_id`.

Examples:

- "Continue debugging Phoenix WebMind"
- "Remember to ask about sleep tomorrow"
- "Explore music/video tooling ideas later"

### Continuity Note

Small append-only note tied to an agent and optional thread.

Use for:

- quick facts that matter now
- recovery breadcrumbs
- short reflective anchors

## Data Model Principles (v0)

1. All records are scoped by `agent_id`.
2. All writes record `actor`, `source`, and timestamps.
3. Handoffs and notes are append-only.
4. Threads are mutable but keep status transitions explicit.
5. Include correlation IDs when writes originate from Phoenix packets.

## Proposed Tables (v0)

The exact SQL can change, but the shape should stay stable.

### `wm_identity_anchor_snapshot`

Purpose:

- cache/record latest identity anchor summary per agent for fast `mind_orient`

Fields:

- `agent_id` (PK component)
- `identity_version_hash` (string)
- `anchor_summary` (text)
- `constraints_summary` (text, optional)
- `updated_at` (timestamp)
- `source` (string; e.g. `brain`, `system`, `manual`)

Notes:

- v0 may treat this as a simple upsert table
- values can be seeded from Brain identity YAML at startup or on demand

### `wm_session_handoffs`

Purpose:

- append-only continuity checkpoints

Fields:

- `handoff_id` (UUID)
- `agent_id` (indexed)
- `thread_id` (nullable; chat thread/session if applicable)
- `title` (short summary)
- `summary` (what happened)
- `next_steps` (text)
- `open_loops` (text)
- `state_hint` (nullable; e.g. `supportive`, `practical`, `reflective`)
- `actor` (`human|agent|system`)
- `source` (`discord|webui|system|autonomy`)
- `correlation_id` (nullable; packet_id or run_id)
- `created_at` (timestamp)

### `wm_mind_threads`

Purpose:

- active persistent intentions/commitments

Fields:

- `thread_key` (UUID or stable string id)
- `agent_id` (indexed)
- `title` (string)
- `description` (text)
- `status` (`open|paused|resolved|archived`)
- `priority` (int, default 5)
- `lane` (nullable; `bond|life|growth|creative|ops`)
- `last_touched_at` (timestamp)
- `created_at` (timestamp)
- `updated_at` (timestamp)
- `created_by_actor` (`human|agent|system`)
- `updated_by_actor` (`human|agent|system`)
- `source` (string)
- `correlation_id` (nullable)

### `wm_thread_events`

Purpose:

- append-only history for thread changes (status updates, notes, edits)

Fields:

- `event_id` (UUID)
- `thread_key` (indexed)
- `agent_id` (indexed)
- `event_type` (`created|updated|status_changed|note_added`)
- `event_summary` (text)
- `payload_json` (text/json)
- `actor` (`human|agent|system`)
- `source` (string)
- `correlation_id` (nullable)
- `created_at` (timestamp)

### `wm_continuity_notes`

Purpose:

- fast append-only notes for recovery/grounding

Fields:

- `note_id` (UUID)
- `agent_id` (indexed)
- `thread_key` (nullable)
- `note_type` (`continuity|reflection|memory_anchor|ops`)
- `content` (text)
- `salience` (`low|normal|high`) default `normal`
- `actor` (`human|agent|system`)
- `source` (string)
- `correlation_id` (nullable)
- `created_at` (timestamp)

## Proposed HTTP Endpoints (WebMind v0)

These map cleanly to future MCP tools.

### `GET /health`

Returns:

- `status`
- `service`
- `version`
- `timestamp`

### `GET /mind/orient`

Query params:

- `agent_id` (required)

Purpose:

- continuity recovery read

Response shape (high-level):

- identity anchor summary
- latest handoff (if any)
- active thread count and top threads
- recent continuity notes

### `GET /mind/ground`

Query params:

- `agent_id` (required)
- `limit` (optional; default 5)

Purpose:

- actionable grounding snapshot (open threads + recent handoffs/notes)

### `POST /mind/session-handoffs`

Purpose:

- write a structured handoff/checkpoint

Body fields (v0 draft):

- `agent_id`
- `thread_id` (optional)
- `title`
- `summary`
- `next_steps`
- `open_loops`
- `state_hint` (optional)
- `actor`
- `source`
- `correlation_id` (optional)

### `GET /mind/session-handoffs`

Query params:

- `agent_id` (required)
- `limit` (optional; default 5)

Purpose:

- retrieve recent handoffs

### `GET /mind/threads`

Query params:

- `agent_id` (required)
- `status` (optional; default `open`)
- `limit` (optional)

Purpose:

- list active threads

### `POST /mind/threads/upsert`

Purpose:

- create or update a thread in one endpoint for v0 simplicity

Body fields (v0 draft):

- `agent_id`
- `thread_key` (optional for create)
- `title`
- `description` (optional)
- `status` (optional)
- `priority` (optional)
- `lane` (optional)
- `actor`
- `source`
- `correlation_id` (optional)

Behavior:

- if `thread_key` missing: create thread + emit `created` event
- if `thread_key` present: update thread + emit `updated` or `status_changed` event

### `POST /mind/notes`

Purpose:

- append a continuity note

Body fields (v0 draft):

- `agent_id`
- `thread_key` (optional)
- `note_type`
- `content`
- `salience` (optional)
- `actor`
- `source`
- `correlation_id` (optional)

## Proposed MCP Tool Mapping (Slice 7 target, names reserved now)

Reserve these names now to avoid drift:

- `mind_orient` -> `GET /mind/orient`
- `mind_ground` -> `GET /mind/ground`
- `mind_session_handoff_write` -> `POST /mind/session-handoffs`
- `mind_session_handoff_read` -> `GET /mind/session-handoffs`
- `mind_thread_list` -> `GET /mind/threads`
- `mind_thread_upsert` -> `POST /mind/threads/upsert`
- `mind_note_add` -> `POST /mind/notes`

## Proposed Pydantic Contract Names (for Slice 2 implementation)

WebMind-local contracts (can move to `shared/` later if needed):

- `MindOrientResponse`
- `MindGroundResponse`
- `SessionHandoffWriteRequest`
- `SessionHandoffRecord`
- `MindThreadUpsertRequest`
- `MindThreadRecord`
- `MindThreadEventRecord`
- `ContinuityNoteWriteRequest`
- `ContinuityNoteRecord`

## Correlation & Actor Metadata (Required on Writes)

Every write request should accept:

- `actor`: `human | agent | system`
- `source`: `discord | webui | system | autonomy | api`
- `correlation_id` (optional)

Usage:

- set `correlation_id = packet_id` when write originates from a `ThoughtPacket`
- set `correlation_id = autonomy_run_id` for autonomy workflows

## Retrieval Behavior (v0 Deterministic)

### `mind_orient` ordering

1. latest identity anchor snapshot
2. latest handoff
3. top open threads by priority + recency
4. recent high-salience continuity notes

### `mind_ground` ordering

1. open threads sorted by priority desc, `last_touched_at` desc
2. recent handoffs desc
3. recent notes desc

No semantic search/ranking in v0.

## Future Compatibility Notes

This v0 shape is designed to expand without breaking names:

- Slice 3 adds `life_*` tables and endpoints
- Slice 4 adds `bond_*` tables and endpoints
- Slice 5 adds `autonomy_*` run and schedule tables
- Slice 6 adds journals/patterns/insights and optional embeddings

## Slice 2 Build Checklist (Derived from This Sketch)

- create `services/webmind` FastAPI app with `/health`
- add v0 DB schema migration(s)
- implement handoff + thread + note repositories
- implement `mind_orient` and `mind_ground` read models
- add tests for write/read ordering and agent scoping
- document Brain integration strategy (fail-open if WebMind unavailable)

