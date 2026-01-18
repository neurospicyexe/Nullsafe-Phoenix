# Nullsafe Phoenix v2 Day One Kernel

Reliability-first agent orchestration system with strict architectural separation.

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Discord   │──────│     VPS     │──────│ Workstation │
│     Bot     │ HTTP │    Relay    │ HTTP │    Brain    │
└─────────────┘      └─────────────┘      └─────────────┘
       │                    │                     │
       │                    │                     │
    Redis ◄──────────── Redis              Identity Files
    Outbox               Queues             + Obsidian
```

## Components

### VPS Relay (`services/relay/`)
- Always-on buffering and retry layer
- Fast path: Immediate forward to Brain (5s timeout)
- Queue path: Durable queueing with crash-safe retries
- **Never**: Calls Discord, loads identity, runs LLM inference

### Workstation Brain (`services/brain/`)
- All agent intelligence and decision-making
- Deterministic identity loading from YAML files
- Sandboxed Obsidian writes
- **Never**: Depends on Redis, talks to Discord

### Discord Bot (`services/discord_bot/`)
- ONLY component that talks to Discord API
- Converts messages to ThoughtPackets
- Consumes outbox with crash-safe retry
- **Never**: Calls Brain directly, loads identity, runs inference

### Shared Contracts (`shared/`)
- `ThoughtPacket`: Request format with validation
- `AgentReply`: Response format
- `QueueEnvelope`: Retry state preservation

## Project Structure

```
nullsafe-phoenix/
├── shared/
│   ├── contracts.py           # Pydantic models
│   ├── tests/
│   │   └── test_contracts.py
│   └── requirements.txt
├── services/
│   ├── relay/
│   │   ├── requirements.txt
│   │   └── tests/
│   ├── brain/
│   │   ├── requirements.txt
│   │   └── tests/
│   └── discord_bot/
│       ├── requirements.txt
│       └── tests/
├── pytest.ini
└── README.md
```

## Setup

### Install Dependencies

```bash
# Shared contracts
cd shared && pip install -r requirements.txt

# Relay service
cd services/relay && pip install -r requirements.txt

# Brain service
cd services/brain && pip install -r requirements.txt

# Discord bot
cd services/discord_bot && pip install -r requirements.txt
```

### Run Tests

```bash
# From project root
pytest

# Run specific test file
pytest shared/tests/test_contracts.py -v

# Run with coverage
pytest --cov=shared --cov=services
```

## Reliability Guarantees

✅ **Never drops messages silently**
- Every message → ThoughtPacket with packet_id
- Durable queueing in Redis with envelopes
- Crash-safe RPOPLPUSH operations
- Dead-letter queues for undeliverable packets

✅ **Dedupe with TTL**
- Per-packet SETEX keys (24h TTL)
- `phx:dedupe:ingest:<packet_id>` prevents duplicate ingestion
- `phx:dedupe:outbox:<packet_id>` prevents duplicate Discord sends

✅ **Observable state**
- `/status` endpoint exposes queue depths
- All logs searchable by packet_id
- Queue inspection via redis-cli

## Redis Queues

All keys prefixed with `phx:`

**Incoming (Relay → Brain):**
- `phx:incoming:queue` - Pending packets
- `phx:incoming:inflight` - Currently processing
- `phx:incoming:deadletter` - Failed after N retries

**Outbox (Brain → Discord):**
- `phx:outbox:{thread_id}` - Pending replies
- `phx:outbox:inflight:{channel_id}` - Currently sending
- `phx:outbox:deadletter` - Failed after N retries

**Dedupe:**
- `phx:dedupe:ingest:<packet_id>` - 24h TTL
- `phx:dedupe:outbox:<packet_id>` - 24h TTL

## Environment Variables

### Relay
```bash
REDIS_URL=redis://localhost:6379
BRAIN_SERVICE_URL=http://localhost:8001
```

### Brain
```bash
OBSIDIAN_VAULT_PATH=/path/to/obsidian-vault
IDENTITY_DIR=./services/brain/identity/data
```

### Discord Bot
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
RELAY_URL=http://localhost:8000
REDIS_URL=redis://localhost:6379
```

## What We're NOT Building (Day One)

- ❌ Memory graphs
- ❌ Resurrection compression
- ❌ Heartbeat autonomy
- ❌ Web search / RAG
- ❌ Spotify integration
- ❌ Cross-agent chatter
- ❌ Web UI (Phase Two)

## License

MIT
