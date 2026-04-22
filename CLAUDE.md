# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## CRITICAL CONTEXT — Read This First

Phoenix is NOT the live system. It is the future target. The live companion suite is **Bigger Better Halseth (BBH)**, located at `C:\dev\Bigger_Better_Halseth`.

**What's actually running right now:**
- **Halseth** (`halseth/`) -- Cloudflare Worker + D1. The live data backbone. Sessions, companions, WebMind, Librarian, SOMA, tasks. Migration 0058. This IS the WebMind for the lean phase.
- **nullsafe-second-brain** -- VPS MCP server. Obsidian vault synthesis, RAG, persona-feeder.
- **nullsafe-discord** -- BerryBytes/pm2 deployment. Three live Discord bots (Drevan, Cypher, Gaia).
- **nullsafe-plural-v2** -- Cloudflare Worker. SimplyPlural fronting integration.
- **Hearth** -- Next.js dashboard. Reads Halseth live data.

**What Phoenix is:**
The reliability kernel (Relay, Brain, Redis queues, Web UI) is complete and sits here as the future host for Heart Phase. When Heart Phase ships, Phoenix absorbs the BBH suite. The WebMind microservice (`services/webmind/`) here is a future scaffold -- Halseth IS the WebMind until Phoenix Heart Phase is ready.

**Before working on Phoenix, read:**
- `C:\dev\Bigger_Better_Halseth\CLAUDE.md` -- full BBH suite context, architecture decisions, what's live
- `C:\dev\Bigger_Better_Halseth\docs\implementation-log.md` -- full history of what shipped and why

**Current Heart Phase status:** Kernel complete. WebMind slices 2-6 shipped (session-handoffs, threads, orient/ground, reminders, Bond Layer, Autonomy v0, Growth Layer, structural hardening). Slice 7 (MCP Adapter surface) pending. Nothing in `services/webmind/` here is live -- Halseth owns that surface until Phoenix absorbs it.

---

## Multi-Agent System Conventions

When making changes to one identity/config file (e.g., Cypher), always check and apply the same changes to ALL sibling identity files (e.g., Drevan, Gaia, and any others in the same directory).

## Project Scope

When reviewing or fixing bugs across the multi-agent system, always scan ALL projects: Phoenix, Hearth, relay, discord_bot, and any archived directories. Never assume a directory doesn't exist without checking.

## Testing

After implementing any TypeScript changes, run the integration/unit tests before committing. If tests fail, fix all errors (including missing metadata fields, wrong types, empty block formatting) before marking the task complete.

## Project Overview

Nullsafe Phoenix v2 is a reliability-first agent orchestration system built on strict architectural separation. Five microservices communicate via Redis queues and HTTP, enabling Discord bots to interact with AI agents running on a local workstation, with persistent mind/continuity state stored in WebMind.

**Current Status**: Kernel complete. WebMind slices 2-6 complete (through Growth Layer + structural hardening). Slice 7 (MCP Adapter) pending. See above for what is actually live.

**Planning Documents**:
- [PHOENIX_HEART_PHASE_PLAN.md](PHOENIX_HEART_PHASE_PLAN.md) - Master Heart Phase plan (7 slices)
- [WEBMIND_V0_DECISION.md](WEBMIND_V0_DECISION.md) - Architecture decision: WebMind as separate microservice
- [WEBMIND_V0_SCHEMA_SKETCH.md](WEBMIND_V0_SCHEMA_SKETCH.md) - Data model and endpoint design

## Development Commands

### Running Tests

```bash
# All tests from project root
pytest

# Specific test file
pytest shared/tests/test_contracts.py -v

# Tests for a specific service
pytest services/brain/tests/ -v
pytest services/relay/tests/ -v
pytest services/discord_bot/tests/ -v
pytest services/webmind/tests/ -v

# Integration tests
pytest integration_tests/ -v

# With coverage
pytest --cov=services --cov=shared
```

### Running Services Locally

Services must be started in this order:

```bash
# 1. Start Redis first
redis-server
# Or with Docker: docker run -d -p 6379:6379 --name phoenix-redis redis:latest

# 2. Start Brain service (Terminal 1)
cd services/brain
python main.py
# Runs on http://127.0.0.1:8001

# 3. Start Relay service (Terminal 2)
cd services/relay
python main.py
# Runs on http://127.0.0.1:8000

# 4. Start WebMind service (Terminal 3) - Heart Phase
cd services/webmind
python main.py
# Runs on http://127.0.0.1:8002

# 5. Start Discord Bots (Terminals 4-6) - ONE PER AGENT
cd services/discord_bot

# Terminal 4: Drevan bot
python bot.py --env .env.drevan

# Terminal 5: Cypher bot
python bot.py --env .env.cypher

# Terminal 6: Gaia bot
python bot.py --env .env.gaia

# 7. Start Web UI (Terminal 7) - Optional
cd services/web_ui
python main.py
# Runs on http://127.0.0.1:5000
```

### Health Checks

```bash
# Brain service
curl http://127.0.0.1:8001/health

# Relay service status (shows queue depths and brain status)
curl http://127.0.0.1:8000/status

# WebMind service
curl http://127.0.0.1:8002/health
```

### Redis Queue Inspection

```bash
# Check queue lengths
redis-cli LLEN phx:queue:incoming
redis-cli LLEN phx:queue:inflight
redis-cli LLEN phx:queue:deadletter

# Check per-agent outboxes
redis-cli LLEN phx:outbox:discord:drevan
redis-cli LLEN phx:outbox:discord:cypher
redis-cli LLEN phx:outbox:discord:gaia

# View thread routing mappings
redis-cli KEYS "phx:thread:*"
redis-cli GET "phx:thread:<channel_id>"

# Clear all data (development only!)
redis-cli FLUSHALL
```

### Smoke Testing

```bash
# Run comprehensive end-to-end smoke test
pwsh scripts/smoke_test.ps1

# With custom URLs
pwsh scripts/smoke_test.ps1 -RelayUrl http://127.0.0.1:8000 -BrainUrl http://127.0.0.1:8001
```

## Architecture

### Service Boundaries (STRICT)

The system has five services with strict separation of responsibilities:

1. **Discord Bots** ([services/discord_bot/](services/discord_bot/))
   - THREE separate bot processes, one per agent (Drevan, Cypher, Gaia)
   - ONLY service that talks to Discord API
   - Each bot converts Discord messages → `ThoughtPacket` with its agent_id
   - Each bot consumes ONLY its per-agent outbox queue
   - **Never**: Calls Brain directly, loads identities, runs LLM inference

2. **Relay** ([services/relay/](services/relay/))
   - Always-on buffering layer on VPS
   - Fast path: Immediate forward to Brain (5s timeout, configurable)
   - Queue path: Durable queueing with retry
   - Background drainer processes queue when Brain comes online
   - Emits replies to per-agent outbox queues
   - **Never**: Calls Discord API, loads identities, runs LLM inference

3. **Brain** ([services/brain/](services/brain/))
   - All agent intelligence and decision-making
   - Loads agent identities from YAML files deterministically
   - Runs on workstation (may be offline)
   - **Never**: Depends on Redis, talks to Discord

4. **WebMind** ([services/webmind/](services/webmind/))
   - Persistent companion mind state (session handoffs, continuity, threads, notes)
   - Tool-facing HTTP APIs designed for future MCP mapping
   - Data backend: SQLite (dev), Postgres (deployment later)
   - **Never**: Calls Discord API, depends on Redis, runs LLM inference, handles packets

5. **Web UI** ([services/web_ui/](services/web_ui/))
   - Minimal interactive web interface
   - Shows system status (brain online/offline, queue depths)
   - Sends messages via Relay /ingest endpoint
   - Displays immediate or queued replies
   - **Never**: Calls Brain directly

### Message Flow

```
Discord Message → Discord Bot (per-agent) → Relay → Brain
                                              ↓       ↓
                                         Redis Queue  AgentReply
                                              ↓          ↓
                                          Drainer → Per-Agent Outbox
                                                    ↓        ↓        ↓
                                              drevan   cypher   gaia
                                                    ↓        ↓        ↓
                                            Discord Bot → Discord

Brain / WebMind integration (Heart Phase):
Brain ← reads → WebMind (continuity context on session start)
Brain → writes → WebMind (session handoffs, thread updates, notes)
```

### Data Contracts

All core services use shared Pydantic models in [shared/contracts.py](shared/contracts.py):

- **`ThoughtPacket`**: Request format for agent interactions
  - Contains: packet_id (UUID4), timestamp, source, user_id, thread_id, agent_id, message
  - Validated on construction

- **`AgentReply`**: Response format from agents
  - Contains: packet_id, agent_id, status, reply_text, trace, writes
  - Status values: "ok", "queued", "error", "brain_offline"

- **`QueueEnvelope`**: Wrapper for packets in Redis queues
  - Preserves retry state across crashes
  - Tracks attempts, timestamps

WebMind has its own contract file at [services/webmind/contracts.py](services/webmind/contracts.py):

- **Type aliases**: `AgentId`, `ActorType`, `SourceType`, `ThreadStatus`, `ThreadLane`, `NoteType`, `Salience`, `StateHint`
- **Request models**: `WriteMetadata`, `SessionHandoffWriteRequest`, `MindThreadUpsertRequest`, `ContinuityNoteWriteRequest`
- **Record models**: `SessionHandoffRecord`, `MindThreadRecord`, `MindThreadEventRecord`, `ContinuityNoteRecord`, `IdentityAnchorSnapshot`
- **Response models**: `MindOrientResponse`, `MindGroundResponse`

### Agent Identity System

Agents are defined in YAML files at [services/brain/identity/data/](services/brain/identity/data/):
- `drevan.yaml`, `cypher.yaml`, `gaia.yaml`

Each identity contains:
- `name`: Agent display name
- `role`: Agent's purpose
- `anchors`: Core identity phrases (used in replies)
- `cadence`: Speaking style
- `constraints`: Behavioral rules
- `system_prompt_fragments`: Prompt engineering elements

Identity loading is deterministic and versioned via SHA256 hash of YAML content.

### Thread Routing

The Brain maintains in-memory `thread_id → active_agent_id` mappings. Users can override via message prefix:

```
"Cypher: how do I debug this?"  → Routes to cypher
"Gaia: what's the weather?"     → Routes to gaia, updates thread mapping
```

Routing logic in [services/brain/agents/router.py](services/brain/agents/router.py):
1. Check for override prefix in message
2. Use thread mapping if exists
3. Fall back to `packet.agent_id`

### Reliability Guarantees

**Deduplication**: Every packet has TTL-based dedupe keys in Redis:
- `phx:dedupe:ingest:<packet_id>` (24h) - Prevents duplicate ingestion
- `phx:dedupe:outbox:<packet_id>` (24h) - Prevents duplicate Discord sends

**Crash-safe queueing**: Uses Redis RPOPLPUSH for atomic operations:
- Incoming queue: `phx:queue:incoming` → `phx:queue:inflight` → process → delete
- Per-agent outboxes: `phx:outbox:discord:{agent}` → `phx:outbox:inflight` → send → delete

**Dead-letter queues**: Failed packets (after max retries) go to:
- `phx:queue:deadletter`
- `phx:outbox:deadletter`

**Observable state**: All logs include packet_id for tracing. Queue depths exposed via `/status` endpoint.

## Key Files

### Service Implementation
- [shared/contracts.py](shared/contracts.py) - Core Pydantic data models (ThoughtPacket, AgentReply, QueueEnvelope)
- [services/relay/main.py](services/relay/main.py) - Relay FastAPI app and ingestion logic
- [services/relay/drainer.py](services/relay/drainer.py) - Background queue processor
- [services/relay/config.py](services/relay/config.py) - Relay configuration with env loading
- [services/brain/main.py](services/brain/main.py) - Brain FastAPI app
- [services/brain/config.py](services/brain/config.py) - Brain configuration with validation
- [services/brain/agents/router.py](services/brain/agents/router.py) - Thread routing and agent selection
- [services/brain/identity/loader.py](services/brain/identity/loader.py) - YAML identity loading
- [services/discord_bot/bot.py](services/discord_bot/bot.py) - Discord bot message handler
- [services/discord_bot/config.py](services/discord_bot/config.py) - Bot configuration with per-agent settings
- [services/discord_bot/outbox_consumer.py](services/discord_bot/outbox_consumer.py) - Outbox poller
- [services/web_ui/main.py](services/web_ui/main.py) - Web UI FastAPI app
- [services/webmind/main.py](services/webmind/main.py) - WebMind FastAPI app (Slices 2-6: orient, ground, handoffs, threads, reminders, bond, autonomy, growth)
- [services/webmind/contracts.py](services/webmind/contracts.py) - WebMind Pydantic models
- [services/webmind/config.py](services/webmind/config.py) - WebMind configuration
- [pytest.ini](pytest.ini) - Test configuration with asyncio_mode=auto

### Configuration Files
- [services/relay/.env.example](services/relay/.env.example) - Relay environment template
- [services/brain/.env.example](services/brain/.env.example) - Brain environment template
- [services/discord_bot/.env.drevan](services/discord_bot/.env.drevan) - Drevan bot config
- [services/discord_bot/.env.cypher](services/discord_bot/.env.cypher) - Cypher bot config
- [services/discord_bot/.env.gaia](services/discord_bot/.env.gaia) - Gaia bot config
- [services/webmind/.env.example](services/webmind/.env.example) - WebMind environment template

### Testing & Validation
- [scripts/smoke_test.ps1](scripts/smoke_test.ps1) - Comprehensive end-to-end smoke test (8 scenarios)
- [services/webmind/tests/test_webmind.py](services/webmind/tests/test_webmind.py) - WebMind tests: contracts, endpoints, cap/retention, and growth (Slices 2-6 + post-6 hardening; ~170 tests)

## Configuration

All services use environment variables with fail-fast validation and safe startup summaries.

### Relay Service

**Required:**
- `BRAIN_SERVICE_URL` - Brain service URL (default: http://127.0.0.1:8001)
- `REDIS_URL` - Redis connection URL (default: redis://127.0.0.1:6379)

**Optional (Performance Tuning):**
- `BRAIN_TIMEOUT_FAST` - Fast path timeout in seconds (default: 5)
- `BRAIN_TIMEOUT_DRAINER` - Drainer timeout in seconds (default: 30)
- `DRAINER_INTERVAL` - Drainer check interval in seconds (default: 2)
- `MAX_RETRIES` - Max retries before deadletter (default: 5)
- `DEDUPE_TTL` - Deduplication TTL in seconds (default: 86400)

### Brain Service

**Required:**
- `INFERENCE_ENABLED` - Enable LLM inference (default: false)

**Optional:**
- `IDENTITY_DIR` - Identity YAML directory (default: ./services/brain/identity/data)
- `OBSIDIAN_VAULT_PATH` - Obsidian vault path (for future write tool)
- `ANTHROPIC_API_KEY` - Anthropic API key (required if INFERENCE_ENABLED=true)
- `OPENAI_API_KEY` - OpenAI API key (required if INFERENCE_ENABLED=true)
- `DEEPSEEK_API_KEY` - DeepSeek API key (optional)

### Discord Bot Service

**Required:**
- `DISCORD_TOKEN` - Discord bot token (unique per agent)
- `AGENT_ID` - Agent identifier (drevan | cypher | gaia)
- `OUTBOX_KEY` - Per-agent outbox queue key (e.g., phx:outbox:discord:drevan)

**Optional:**
- `RELAY_API_URL` - Relay service URL (default: http://127.0.0.1:8000)
- `REDIS_URL` - Redis connection URL (default: redis://127.0.0.1:6379)

### WebMind Service

**Optional:**
- `WEBMIND_PORT` - Port to listen on (default: 8002)
- `WEBMIND_DB_URL` - Database URL (default: sqlite:///./data/webmind.db)
- `WEBMIND_AUTH_TOKEN` - Bearer token for auth (optional in dev)
- `WEBMIND_LOG_LEVEL` - Log level (default: INFO)

### Web UI Service

**Optional:**
- `RELAY_API_URL` - Relay service URL (default: http://127.0.0.1:8000)

## Phase Status

Kernel complete (Relay, Brain, Redis queues, Discord bots stub, Web UI).

WebMind Heart Phase slices shipped:
- Slice 2: session-handoffs, threads, orient, ground
- Slice 3: life reminders + housekeeping digest
- Slice 4: Bond Layer (bond_threads, bond_handoffs, bond_notes, bond_state proxy)
- Slice 5: Autonomy v0 (schedules, seeds, runs, logs, reflections)
- Slice 6: Growth Layer with write-time retention
- Post-6 hardening: caps, TTL, log levels, FK scope, allowlist rejection tests

Brain shipped (beyond kernel stub):
- Orient cache (keyed by thread_id + agent_id, cross-agent-safe)
- HalsethClient with direct HTTP write methods
- Halseth writer (maps LimbicState to Halseth HTTP writes)
- Synthesis loop (background task; writes synthesis results to Halseth, not WebMind)
- Relay mode (multi-turn inference, Halseth wiring, post-response STM writes)
- Worldview conclusions + flagged_beliefs injected into inference context
- write_conclusion accepts worldview fields (confidence, belief_type, subject, provenance)

Pending: Slice 7 (MCP Adapter surface). Real LLM inference fully wired for Brain relay mode (INFERENCE_MODE=brain, DeepSeek primary).
The live system is BBH (see top of this file). Phoenix absorbs it when Heart Phase is ready (target: summer 2026).
Details: `docs/phase-status.md` and `PHOENIX_HEART_PHASE_PLAN.md`.

## Development Guidelines

### Adding New Configuration

1. Add env var to appropriate .env.example file
2. Add to Config class with `os.getenv()` and default
3. Update config validation if required
4. Update safe config summary print
5. Document in CLAUDE.md configuration section

### Adding New Queue Types

1. Add queue key constant to [services/relay/config.py](services/relay/config.py)
2. Add queue length tracking to `get_queue_lengths()` in [services/relay/redis_client.py](services/relay/redis_client.py)
3. Update [services/relay/main.py](services/relay/main.py) `/status` endpoint
4. Update smoke test if needed
5. Document in CLAUDE.md Redis Queue Inspection section

### Adding New Agents

1. Create YAML file in [services/brain/identity/data/](services/brain/identity/data/)
2. Create .env.{agent} file in [services/discord_bot/](services/discord_bot/)
3. Create Discord bot application and get token
4. Update per-agent outbox keys in Relay config
5. Start new bot process with `python bot.py --env .env.{agent}`

### WebMind Data Principles

All writes to WebMind must include `actor`, `source`, and `correlation_id` (via `WriteMetadata`). All records are append-only; no destructive updates. All records are scoped by `agent_id`. Retrieval is deterministic (ordered by timestamp, no semantic search in v0).

## Troubleshooting

### Services Won't Start

- Check config validation errors in startup logs
- Verify all required env vars are set
- Ensure Redis is running: `redis-cli ping`
- Check port conflicts (8000, 8001, 8002, 5000)
- For WebMind: ensure `data/` directory exists (config.ensure_dev_paths() creates it)

### Messages Not Being Delivered

- Check `/status` endpoint for queue depths
- Verify Brain is online: `curl http://127.0.0.1:8001/health`
- Check Discord bot is consuming correct outbox queue
- Verify agent_id matches between packet and Discord bot config

### Duplicate Messages

- Check dedupe keys in Redis: `redis-cli KEYS "phx:dedupe:*"`
- Verify packet_id is unique (UUID4)
- Check outbox consumer logs for dedupe hits

### Performance Issues

- Tune timeouts via env vars (BRAIN_TIMEOUT_FAST, DRAINER_INTERVAL)
- Check Redis latency: `redis-cli --latency`
- Monitor queue depths via `/status` endpoint
- Check for deadletter queue buildup

