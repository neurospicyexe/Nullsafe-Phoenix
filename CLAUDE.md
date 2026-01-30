# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nullsafe Phoenix v2 is a reliability-first agent orchestration system built on strict architectural separation. Three microservices communicate via Redis queues and HTTP, enabling a Discord bot to interact with AI agents running on a local workstation.

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
# Runs on http://localhost:8001

# 3. Start Relay service (Terminal 2)
cd services/relay
python main.py
# Runs on http://localhost:8000

# 4. Start Discord Bot (Terminal 3)
export DISCORD_TOKEN=your_token_here  # or 'set' on Windows
cd services/discord_bot
python bot.py
```

### Health Checks

```bash
# Brain service
curl http://localhost:8001/health

# Relay service status (shows queue depths)
curl http://localhost:8000/status
```

### Redis Queue Inspection

```bash
# Check queue lengths
redis-cli LLEN phx:incoming:queue
redis-cli LLEN phx:incoming:inflight
redis-cli LLEN phx:incoming:deadletter
redis-cli LLEN phx:outbox:discord

# View thread routing mappings
redis-cli KEYS "phx:thread:*"
redis-cli GET "phx:thread:<channel_id>"

# Clear all data (development only!)
redis-cli FLUSHALL
```

## Architecture

### Service Boundaries (STRICT)

The system has three services with strict separation of responsibilities:

1. **Discord Bot** ([services/discord_bot/](services/discord_bot/))
   - ONLY service that talks to Discord API
   - Converts Discord messages → `ThoughtPacket`
   - Consumes outbox and sends replies to Discord
   - **Never**: Calls Brain directly, loads identities, runs LLM inference

2. **Relay** ([services/relay/](services/relay/))
   - Always-on buffering layer on VPS
   - Fast path: Immediate forward to Brain (5s timeout)
   - Queue path: Durable queueing with retry
   - Background drainer processes queue when Brain comes online
   - **Never**: Calls Discord API, loads identities, runs LLM inference

3. **Brain** ([services/brain/](services/brain/))
   - All agent intelligence and decision-making
   - Loads agent identities from YAML files deterministically
   - Runs on workstation (may be offline)
   - **Never**: Depends on Redis, talks to Discord

### Message Flow

```
Discord Message → Discord Bot → Relay → Brain
                                  ↓       ↓
                             Redis Queue  AgentReply
                                  ↓          ↓
                              Drainer → Outbox → Discord Bot → Discord
```

### Data Contracts

All services use shared Pydantic models in [shared/contracts.py](shared/contracts.py):

- **`ThoughtPacket`**: Request format for agent interactions
  - Contains: packet_id (UUID4), timestamp, source, user_id, thread_id, agent_id, message
  - Validated on construction

- **`AgentReply`**: Response format from agents
  - Contains: packet_id, agent_id, status, reply_text, trace, writes
  - Status values: "ok", "queued", "error", "brain_offline"

- **`QueueEnvelope`**: Wrapper for packets in Redis queues
  - Preserves retry state across crashes
  - Tracks attempts, timestamps

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
- Incoming queue: `phx:incoming:queue` → `phx:incoming:inflight` → process → delete
- Outbox queue: `phx:outbox:discord` → `phx:outbox:inflight` → send → delete

**Dead-letter queues**: Failed packets (after max retries) go to:
- `phx:incoming:deadletter`
- `phx:outbox:deadletter`

**Observable state**: All logs include packet_id for tracing. Queue depths exposed via `/status` endpoint.

## Key Files

- [shared/contracts.py](shared/contracts.py) - Pydantic data models
- [services/relay/main.py](services/relay/main.py) - Relay FastAPI app and ingestion logic
- [services/relay/drainer.py](services/relay/drainer.py) - Background queue processor
- [services/brain/main.py](services/brain/main.py) - Brain FastAPI app
- [services/brain/agents/router.py](services/brain/agents/router.py) - Thread routing and agent selection
- [services/brain/identity/loader.py](services/brain/identity/loader.py) - YAML identity loading
- [services/discord_bot/bot.py](services/discord_bot/bot.py) - Discord bot message handler
- [services/discord_bot/outbox_consumer.py](services/discord_bot/outbox_consumer.py) - Outbox poller
- [pytest.ini](pytest.ini) - Test configuration with asyncio_mode=auto

## Configuration

Services use environment variables:

**Relay:**
- `REDIS_URL` (default: redis://localhost:6379)
- `BRAIN_SERVICE_URL` (default: http://localhost:8001)

**Brain:**
- `OBSIDIAN_VAULT_PATH` - Path to Obsidian vault (for future write tool)
- `IDENTITY_DIR` (default: ./services/brain/identity/data)

**Discord Bot:**
- `DISCORD_TOKEN` - Discord bot token (required)
- `RELAY_URL` (default: http://localhost:8000)
- `REDIS_URL` (default: redis://localhost:6379)

## What's NOT Built Yet (Day One Scope)

Day One is a minimal kernel. These are explicitly out of scope:
- LLM inference (returns stub replies with identity anchors)
- Obsidian write tool execution
- Memory graphs
- Web search / RAG
- Cross-agent chatter
- Web UI

The current implementation validates architecture and message flow with stub replies that demonstrate identity selection.
