# WebMind v0 Boundary Decision (Slice 1)

Created: February 24, 2026
Status: **SUPERSEDED** -- This describes Phoenix WebMind as a separate microservice.
The actual v0 implementation landed in Halseth (`halseth/src/webmind/`, wm_* tables, migrations 0027+).
Keep as Heart Phase reference -- when Phoenix absorbs BBH, this interface design still applies.

## Decision

`WebMind` will be introduced as a **new microservice** at `services/webmind`, not as a module inside `services/brain`.

## Why

Phoenix already has strong service boundaries. Folding persistent mind state and tool APIs into `Brain` would create a stateful monolith and blur responsibilities.

Keeping `WebMind` separate protects:

- `Brain` as short-lived reasoning/orchestration
- `Relay` as transport/retry/buffering
- `Discord Bot` as the only Discord API client
- `WebMind` as persistent mind/bond/life/autonomy tool surface

## WebMind v0 Responsibilities (In Scope)

WebMind v0 is a continuity-first slice.

It will own:

- session handoffs (write/read)
- continuity snapshots (`mind_orient`, `mind_ground`)
- active mind threads (list/upsert)
- companion notes for continuity recovery
- persistent storage for the above
- API contracts for future MCP mapping

## WebMind v0 Non-Goals (Out of Scope)

Not in v0:

- direct Discord API access
- Redis queue management
- LLM inference
- embeddings/vector search
- full autonomy scheduler
- broad task/reminder system (belongs to Slice 3)
- rich bond-state layer (belongs to Slice 4)

## Service Boundary Rules

### WebMind MUST

- be independently deployable
- persist long-term state
- validate all request payloads
- log writes with actor/source/correlation metadata
- scope data by `agent_id`

### WebMind MUST NOT

- call Discord directly
- depend on Relay Redis queues for core storage
- own thread routing for live chat replies (Brain keeps conversational routing)
- become a hidden side-channel that bypasses Phoenix observability norms

## Initial Integration Pattern

### Reads (continuity retrieval)

- `Brain` may call `WebMind` at conversation start or before response generation to load continuity context.
- `Web UI` may call `WebMind` directly for dashboards and history views.
- Future MCP clients will call `WebMind` via an adapter or native MCP endpoint.

### Writes (handoffs / thread updates)

- `Brain` (or future orchestration worker) writes handoffs and thread changes to `WebMind`.
- Writes include correlation IDs from the originating packet when available.

## Failure Handling Policy (v0)

WebMind failure should degrade gracefully:

- Chat reply path should continue if `WebMind` is unavailable (continuity reduced, core messaging still works)
- Write failures should be logged and surfaced, not silently swallowed
- No WebMind outage should block Relay queue draining

## API Style Decision (v0)

WebMind v0 will start with **HTTP JSON endpoints** (FastAPI style), with endpoint names and payloads designed so they map cleanly to future MCP tools.

Rationale:

- simpler to test with current Phoenix stack
- easier to integrate with existing services
- keeps MCP support as an adapter concern until Slice 7

## Auth Decision (v0 Planning)

WebMind v0 should support a simple bearer token for service-to-service and trusted UI/client calls.

Open question for implementation:

- single shared token vs per-client tokens

## Data Backend Decision (v0 Planning)

Start with a relational store and deterministic queries.

Default dev option:

- SQLite (fast local iteration)

Deployment-ready option (later):

- Postgres

The schema should avoid backend-specific features in v0 so migration remains straightforward.

## Path Conventions (Locked)

- Service path: `services/webmind/`
- Shared contracts (if promoted to common use): `shared/`
- Slice-specific docs: repo root `WEBMIND_*` (temporary, visible during active design)

## Exit Criteria for This Decision

This decision is considered complete when:

- no ambiguity remains about whether WebMind is a new service
- v0 responsibilities are clearly separated from Brain/Relay/Discord
- v0 APIs can be designed without revisiting the architecture split

