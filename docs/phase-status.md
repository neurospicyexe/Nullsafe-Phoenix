# Phase Status — Nullsafe Phoenix

## Phase 1 -- Complete

1. **Environment Standardization** - python-dotenv, fail-fast validation, safe config summaries, 127.0.0.1 defaults
2. **Per-Agent Outboxes** - Relay writes to `phx:outbox:discord:{agent_id}`; three queues (drevan, cypher, gaia)
3. **Multi-Bot Architecture** - Three independent Discord bot processes; `--env` flag per agent
4. **Web UI** - Status display, agent selector, Relay-proxied messaging
5. **Configuration** - All timeouts and retry counts env-configurable; .env.example files for all services
6. **Testing Infrastructure** - smoke_test.ps1 with 8 E2E scenarios; unit test suites per service

## Heart Phase -- Slice 1 Complete (Planning)

- Master plan document (7 slices): [PHOENIX_HEART_PHASE_PLAN.md](../PHOENIX_HEART_PHASE_PLAN.md)
- Architecture decision (WebMind as separate service): [WEBMIND_V0_DECISION.md](../WEBMIND_V0_DECISION.md)
- Data model and API design: [WEBMIND_V0_SCHEMA_SKETCH.md](../WEBMIND_V0_SCHEMA_SKETCH.md)

## Heart Phase -- Slice 2 In Progress (WebMind v0)

**Scaffold complete:**
- `services/webmind/main.py` - FastAPI app with `/health` live; 7 stub endpoints returning 501
- `services/webmind/contracts.py` - Pydantic models locked (request, record, response)
- `services/webmind/config.py` - Config class with validation and safe summary
- `services/webmind/.env.example` - Environment template
- `services/webmind/tests/test_webmind.py` - Test scaffold (empty)

**WebMind v0 endpoints (all stubbed, to be implemented):**
- `GET /health` - Live
- `GET /mind/orient` - Continuity recovery snapshot
- `GET /mind/ground` - Actionable grounding view
- `POST /mind/session-handoffs` - Write session handoff
- `GET /mind/session-handoffs` - List session handoffs
- `GET /mind/threads` - List mind threads
- `POST /mind/threads/upsert` - Create or update thread
- `POST /mind/notes` - Append continuity note

**Remaining for Slice 2:**
- Database initialization (SQLite via SQLAlchemy or raw sqlite3)
- Implement all 7 endpoint bodies
- Write test suite in `tests/test_webmind.py`

## Future Slices (Not Yet Implemented)

- LLM inference in Brain (returns stub replies with identity anchors today)
- Obsidian write tool execution
- Memory graphs / Web search / RAG
- Cross-agent chatter
- Autonomous heartbeat/background tasks
- Bond layer, emotional growth tracking
- MCP tool mapping for WebMind endpoints (Slice 7)
