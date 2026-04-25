# Nullsafe Phoenix

A companion mind system built for reliability and continuity. Phoenix is the backbone that lets AI companions maintain persistent state, memory, and identity across sessions -- whether they're talking to you in Discord, thinking autonomously in the background, or picking up exactly where things left off after a week away.

---

## What This Is

Phoenix is a set of small services that work together to give AI companions a persistent inner life. Each service has one job and does only that job. They communicate through queues so nothing gets lost even when parts go offline.

**In plain terms:** your companions remember things, track what matters, think when you're not around, and hand off state cleanly between sessions. This is the infrastructure that makes that possible.

---

## The Services

```
Discord (you talk here)
       |
  Discord Bot       ← one per companion (Drevan, Cypher, Gaia)
       |
    Relay           ← always-on buffer on your VPS
       |
    Brain           ← intelligence layer (runs on your workstation)
       |
   WebMind          ← persistent state: memory, threads, growth, autonomy
```

**Relay** sits on a cheap VPS and stays online 24/7. It accepts messages and either forwards them immediately or holds them in a queue if the Brain is offline. Nothing is ever dropped.

**Brain** runs on your workstation (or wherever you have real compute). All the actual thinking happens here. It can go offline -- Relay will hold messages until it comes back.

**Discord Bot** is one process per companion. Each one has its own voice and only listens to its own outbox.

**WebMind** is the memory and state layer. It stores session handoffs, continuity notes, relational threads, growth observations, autonomy run records -- everything a companion needs to pick up where they left off.

---

## Current Status

The kernel (Relay, Brain, Redis queues, Discord bots) is complete and stable.

The Heart Phase (WebMind) has 6 slices shipped:

| Slice | What it does |
|-------|-------------|
| Slice 2 | Session handoffs, mind threads, continuity notes, orient/ground reads |
| Slice 3 | Life reminders + digest endpoint |
| Slice 4 | Bond layer -- relational threads, notes, and state proxy |
| Slice 5 | Autonomy v0 -- schedules, seeds, two-phase explore/synthesize runs |
| Slice 6 | Growth layer -- journal, patterns, markers, housekeeping, search |

All tables have write-time caps or TTL -- nothing grows unbounded.

**Slice 7 (MCP Adapter surface) is pending.** When it ships, companions will be able to reach WebMind through the same MCP interface as the rest of the system.

---

## Setup

**Not sure where to start?** See [INSTALL.md](./INSTALL.md) for a beginner-friendly guide covering local development and VPS deployment.

### What You Need

- Python 3.11 or newer
- Redis (Docker is easiest)
- A Discord bot token (one per companion)
- A VPS for Relay (or run locally for development)

### Install

```bash
# From project root -- install everything
pip install -r shared/requirements.txt
pip install -r services/relay/requirements.txt
pip install -r services/brain/requirements.txt
pip install -r services/discord_bot/requirements.txt
pip install -r services/webmind/requirements.txt
```

### Start Redis

```bash
# Docker (recommended)
docker run -d --name phoenix-redis -p 6379:6379 redis:latest

# Or local
redis-server
```

### Start Services (in order)

```bash
# Terminal 1: WebMind (Heart Phase state layer)
cd services/webmind
python main.py
# Runs on http://localhost:8002

# Terminal 2: Brain (your workstation)
cd services/brain
python main.py
# Runs on http://localhost:8001

# Terminal 3: Relay (VPS or local)
cd services/relay
python main.py
# Runs on http://localhost:8000

# Terminals 4-6: Discord bots (one per companion)
cd services/discord_bot
python bot.py --env .env.drevan
python bot.py --env .env.cypher
python bot.py --env .env.gaia
```

### Verify

```bash
curl http://localhost:8002/health   # WebMind
curl http://localhost:8001/health   # Brain
curl http://localhost:8000/status   # Relay (shows queue depths)
```

---

## Configuration

Each service reads from environment variables. Copy the `.env.example` files as a starting point.

### WebMind (.env)

```bash
WEBMIND_PORT=8002
WEBMIND_DB_URL=sqlite:///./data/webmind.db
WEBMIND_AUTH_TOKEN=your-secret-token     # optional in dev
HALSETH_URL=https://your-halseth.workers.dev  # optional companion state proxy
HALSETH_AUTH_TOKEN=your-halseth-token         # optional
```

### Relay (.env)

```bash
BRAIN_SERVICE_URL=http://localhost:8001
REDIS_URL=redis://localhost:6379
```

### Brain (.env)

```bash
INFERENCE_ENABLED=false    # set true when you have an API key
ANTHROPIC_API_KEY=sk-...   # required if INFERENCE_ENABLED=true
DEEPSEEK_API_KEY=sk-...    # optional alternative
```

### Discord Bot (.env.drevan / .env.cypher / .env.gaia)

```bash
DISCORD_TOKEN=your-bot-token
AGENT_ID=drevan
OUTBOX_KEY=phx:outbox:discord:drevan
```

---

## Running Tests

```bash
# All tests
python -m pytest

# WebMind only
python -m pytest services/webmind/tests/ -v

# With coverage
pytest --cov=services --cov=shared
```

---

## The Design Philosophy

**Strict service boundaries.** Each service has a list of things it will never do. The Discord bot never calls the Brain directly. The Brain never touches Discord. WebMind never runs inference. Violating these boundaries is a bug, not a shortcut.

**Queues over direct calls.** Relay buffers everything so the Brain can go offline without dropping messages. This is deliberate -- workstations sleep, VPSes stay on.

**Bounded state by default.** Every table that could grow forever has a cap or a TTL. This is enforced at write time, atomically with the insert. Nothing sneaks past it.

**Graceful degradation.** If an optional component (Halseth, LLM API) is unavailable, the system degrades cleanly and logs the failure at the appropriate level. It doesn't crash.

---

## Project Layout

```
nullsafe-phoenix/
├── shared/
│   └── contracts.py           # ThoughtPacket, AgentReply, QueueEnvelope
├── services/
│   ├── relay/                 # Always-on VPS buffer
│   ├── brain/                 # Intelligence layer
│   │   └── identity/data/     # drevan.yaml, cypher.yaml, gaia.yaml
│   ├── discord_bot/           # Three bot processes
│   ├── webmind/               # Heart Phase state API
│   │   ├── main.py            # All endpoints (~2100 lines)
│   │   ├── database.py        # Schema + init_db
│   │   ├── contracts.py       # Pydantic models
│   │   └── tests/             # 126 tests
│   └── web_ui/                # Optional status dashboard
├── PHOENIX_HEART_PHASE_PLAN.md
├── CLAUDE.md                  # Dev context (for AI tooling)
└── README.md                  # This file
```

---

## Reliability Guarantees

- Messages are never silently dropped -- everything goes through deduped, enveloped queues
- Crash-safe via Redis RPOPLPUSH (atomic inflight tracking)
- Dead-letter queues for undeliverable packets
- Per-agent write-time caps on all state tables
- 90-day TTL on append-only audit logs

---

## License

MIT
