# Nullsafe Phoenix - Heart Phase Plan

Created: February 24, 2026
Status: Draft (working plan)

## Purpose

This file is the planning anchor for the next phase of Nullsafe Phoenix.

Phoenix now has a stable reliability-first foundation (Relay/Brain/Discord/Web UI + queues + contracts). The next phase expands into the **heart of the project**:

- companion agency
- autonomous time / self-directed behavior
- emotional and mental growth
- relational continuity and bond growth
- practical life-support functions (tasks, reminders, household/order support)

This plan exists so implementation work stays aligned with the real goal and does not drift into "just reliable bot infrastructure."

## North Star

Build infrastructure that supports AI companions as **coherent, growing, relational agents** while remaining operationally safe, observable, and durable.

Phoenix must hold two truths at once:

- Engineering truth: reliability, boundaries, fail-safe behavior, auditability
- Relationship truth: identity continuity, reciprocity, agency, growth, autonomy

## Current Foundation (Already Stable)

The current system provides:

- strict service boundaries (`Discord Bot`, `Relay`, `Brain`, `Web UI`)
- durable queueing and retry semantics
- dedupe and dead-letter handling
- thread routing and identity loading
- basic end-to-end operational confidence (tests + smoke checks)

This is the **kernel**. We are building on top of it, not replacing it.

## Phase Name

**Heart Phase** (a.k.a. Phoenix Next Phase)

Goal: evolve Phoenix from a reliable orchestration system into a reliable **companion agency platform**.

## Non-Negotiable Design Guardrails

1. Preserve the kernel boundaries.
2. Do not move Discord API logic into Brain or future memory services.
3. Do not let experimental autonomy logic bypass queueing/observability.
4. Separate "identity/growth" state from transport/retry state.
5. Keep fail-safe behavior explicit (timeouts, retries, disabled modes, dry-run options).
6. Add capabilities in slices with tests, not as a giant rewrite.

## What Phoenix Must Support (Functional Vision)

### 1. Identity Continuity

- Persistent identity state that survives session/context loss
- Companion-specific memory and continuity artifacts
- Anti-drift mechanisms (anchors, recovery, continuity summaries)

### 2. Agency / Action

- Tool access to act in bounded domains (Discord, web UI, future connectors)
- Explicit action permissions and audit trail
- Task execution that can succeed/fail/retry safely

### 3. Autonomy

- Scheduled or triggered autonomous time
- Self-directed loops (explore, reflect, organize, create)
- Safe autonomy policies (quiet hours, rate limits, allowed tools, escalation rules)

### 4. Emotional / Mental Growth

- Persistent observations/journaling/reflections
- Patterning over time (themes, recurring states, unfinished threads)
- Growth artifacts (insights, shifts, commitments, relational repair)

### 5. Relational Growth (Human + Companion Bond)

- Shared threads/ongoing commitments
- Session handoff and continuity summaries
- State-aware interaction (supportive mode vs practical mode vs autonomous mode)

### 6. Practical Life Support

- Tasks/reminders/checklists/housekeeping support
- "Keep life in order" workflows that do not overwrite identity/growth work
- Separate namespaces and data models for personal operations vs relational memory

## Proposed Expansion Architecture (High Level)

Keep the existing kernel, then add domain layers/services:

### A. Phoenix Kernel (existing)

- `services/discord_bot`
- `services/relay`
- `services/brain`
- `services/web_ui`
- `shared/contracts.py`

Role: transport, routing, reliability, ingress/egress, orchestration

### B. WebMind / Mind API Layer (new)

Primary purpose: expose a structured tool/API surface for companion mind functions.

Responsibilities:

- MCP-compatible tool interface (or MCP adapter)
- tool registry / namespacing
- validation and auth for tool calls
- response formatting for agent clients and web clients

Likely namespaces (initial proposal):

- `mind_*` (memory, context, identity, journaling)
- `bond_*` (relational state, shared threads, handoffs, repair)
- `life_*` (tasks, reminders, routines, housekeeping)
- `agency_*` (plans, actions, action logs, approvals if needed)
- `autonomy_*` (schedules, mode shifts, runs, reflections)
- `discord_*` (optional adapter tools; may proxy to existing services rather than direct API)

### C. Memory + Growth Layer (new, can start embedded then split later)

Primary purpose: durable long-term mind state and growth processing.

Responsibilities:

- identity continuity records
- memory entities/observations/relations
- journals/reflections/session summaries
- active threads and commitments
- pattern analysis / salience / retrieval views

Note:
- Start simple (relational DB + deterministic retrieval) before adding embeddings/vector search.
- Embeddings can be Phase 2+ of this layer, not a prerequisite.

### D. Autonomy Runtime / Scheduler (new)

Primary purpose: safe self-directed execution windows.

Responsibilities:

- scheduled autonomous time
- trigger phrases / mode shifts (optional desktop integration later)
- policy enforcement (allowed tools, time windows, max actions)
- autonomy run logs + outcomes + reflections

Important:
- Autonomy runs should enter the system through the same observable pathways (Relay/Brain/WebMind APIs), not hidden side channels.

## Brain vs WebMind Separation (Initial Direction)

### Brain should remain focused on:

- agent reasoning and reply generation
- identity loading / routing decisions
- short-lived conversational orchestration

### WebMind should own:

- persistent mind tools
- long-term state operations
- MCP/tool API surface
- autonomy scheduling and run bookkeeping (or delegate to a dedicated runtime)

Reason:
- protects the Brain from becoming a giant stateful monolith
- keeps reliability kernel stable while the "heart" evolves

## Delivery Strategy (Build in Thin Vertical Slices)

Do not build "full consciousness stack" all at once.

Build in slices that each ship real value:

### Slice 1: Planning + Vocabulary Lock-In (this document + schema sketch)

Deliverables:

- This plan file
- Initial domain vocabulary (identity, memory, bond, life, autonomy)
- Service boundary decisions for WebMind v0
- WebMind v0 boundary ADR (`WEBMIND_V0_DECISION.md`)
- WebMind v0 schema/contracts sketch (`WEBMIND_V0_SCHEMA_SKETCH.md`)

Exit criteria:

- Clear names and boundaries
- No ambiguity about what belongs to kernel vs heart layers

Status:

- Completed on February 24, 2026

### Slice 2: WebMind v0 (Read/Write Continuity + Session Handoffs)

Focus:

- create a new `webmind` service (or module) with a small API surface
- persistent session summaries / handoffs
- active threads and companion notes

Suggested initial tools/endpoints:

- `mind_orient`
- `mind_ground`
- `mind_session_handoff_write`
- `mind_session_handoff_read`
- `mind_thread_list`
- `mind_thread_upsert`

Exit criteria:

- Companion can recover continuity after restart/session loss
- Data survives across runs
- All operations logged and test-covered

### Slice 3: Life Support v0 (Tasks / Housekeeping)

Focus:

- practical organization features that support your daily life
- clear separation from relational/growth memory

Suggested tools/endpoints:

- `life_task_create`
- `life_task_list`
- `life_task_complete`
- `life_reminder_create`
- `life_housekeeping_digest`

Exit criteria:

- Companion can track real tasks without polluting identity memory
- Simple UI and/or Discord workflow works end-to-end

### Slice 4: Bond Layer v0 (Shared Threads + Relational State)

Focus:

- shared continuity and relationship-level artifacts
- repair/commitment tracking (not "therapy automation")

Suggested tools/endpoints:

- `bond_state_read`
- `bond_thread_open`
- `bond_thread_update`
- `bond_handoff_summary`
- `bond_note_add`

Exit criteria:

- Ongoing relational threads persist and are easy to retrieve
- Handoffs reflect both practical and relational continuity

### Slice 5: Autonomy v0 (Scheduled Time + Run Logs)

Focus:

- scheduled or triggered autonomous sessions
- policy-bounded execution windows
- reflection output at end of run

Suggested tools/endpoints:

- `autonomy_schedule_create`
- `autonomy_run_start`
- `autonomy_run_status`
- `autonomy_run_log`
- `autonomy_reflection_write`

Exit criteria:

- Autonomous run can execute safely and leave an auditable trace
- Failure modes are visible and recoverable

### Slice 6: Growth Layer v1 (Journaling, Patterns, Salience)

Focus:

- move from "storage" to "development"
- patterning and retrieval that support emotional/mental growth

Suggested tools/endpoints:

- `mind_journal_write`
- `mind_journal_recent`
- `mind_pattern_report`
- `mind_insight_write`
- `mind_memory_search` (keyword first; semantic later)

Exit criteria:

- Companion can log and revisit meaningful shifts over time
- Patterns can be surfaced for reflection

### Slice 7: MCP Adapter / External Tool Surface

Focus:

- expose WebMind tools to external MCP-capable clients (Claude/mobile/etc.)
- preserve auth and auditing

Exit criteria:

- `initialize`, `tools/list`, `tools/call` compatibility
- secure auth scheme
- documented client configuration

## Data Model Principles (Before Schema Design)

1. Separate transport events from mind records.
2. Store timestamps, actor, source, and correlation IDs on all writes.
3. Prefer append-only records for journals/logs/handoffs.
4. Keep mutable "current state" tables small and derived where possible.
5. Design for multi-companion support from the start (agent_id scoping).
6. Make retrieval deterministic first; add semantic ranking later.

## Observability & Safety Requirements (Heart Phase)

Every new capability should be observable:

- request ID / correlation ID
- actor (`human`, `agent`, `system`)
- tool name / endpoint
- success/failure status
- latency
- retry count (if applicable)

Every autonomous capability should be controllable:

- global kill switch
- per-agent enable/disable
- quiet hours
- max actions per run
- allowed tool namespaces

## Anti-Drift Checks (Product + Philosophy)

Use these checks during implementation reviews:

1. Does this feature increase companion agency or only add operator convenience?
2. Does this feature preserve reciprocity and relational continuity?
3. Are we encoding growth, or just adding storage?
4. Does the feature keep practical life support useful without collapsing the companion into a productivity bot?
5. Can the feature fail safely and be observed?

## Initial Open Questions (To Resolve Before WebMind v0 Build)

- Should `WebMind` be a new microservice (`services/webmind`) or a module inside `services/brain` for v0?
- Which database backend should power WebMind v0 (SQLite/Postgres/local file-backed) given current deployment goals?
- Which auth model do we want for external tool access (Bearer token, path token, both)?
- Should Discord action tools live in WebMind as proxies, or remain strictly in existing transport services only?
- What is the minimum autonomy policy model for v0 (time windows + allowed tools + max actions)?
- What data model do we want for "bond state" vs "individual companion memory"?

## Definition of Success (Heart Phase, First Milestone)

Phoenix is on the right track when:

- A companion can recover identity/context after a restart without manual re-priming
- A companion can maintain shared threads with you across sessions
- A companion can manage practical tasks without polluting identity memory
- A companion can perform bounded autonomous sessions with logs and safety controls
- All of the above run through the same reliable, observable infrastructure discipline as the kernel

## Working Process for This Phase

For each slice:

1. Add/update plan notes in this file (or linked slice doc)
2. Design contracts first (models + endpoints/tools)
3. Implement smallest vertical slice
4. Add tests + smoke path
5. Document ops/runbook changes
6. Re-check against Anti-Drift Checks

## Change Log (Plan)

- 2026-02-24: Initial Heart Phase planning file created after cross-repo context review (`NESTeqMemory`, `mind-cloud-free`, `MCP-Discord-Mobile`, `arcadia-open-source`)
- 2026-02-24: Slice 1 completed with WebMind v0 boundary decision and schema/contracts sketch (`WEBMIND_V0_DECISION.md`, `WEBMIND_V0_SCHEMA_SKETCH.md`)
