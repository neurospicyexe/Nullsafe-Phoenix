# Nullsafe Phoenix WebMind (Planned)

Status: Planned (Slice 1 complete, Slice 2 next)

## Purpose

`WebMind` is the planned Phoenix service for persistent companion mind state and tool-facing APIs.

It is intentionally separate from `Brain` so Phoenix can preserve:

- `Brain` for reasoning and conversational orchestration
- `WebMind` for long-term continuity, mind tools, and future MCP surface

## v0 Scope (Next Slice)

- continuity reads (`mind_orient`, `mind_ground`)
- session handoffs (write/read)
- active threads (list/upsert)
- continuity notes

## Non-Goals (v0)

- Discord API access
- Redis queue ownership
- LLM inference
- embeddings/vector search
- autonomy scheduling

## Related Planning Docs

- `PHOENIX_HEART_PHASE_PLAN.md`
- `WEBMIND_V0_DECISION.md`
- `WEBMIND_V0_SCHEMA_SKETCH.md`

