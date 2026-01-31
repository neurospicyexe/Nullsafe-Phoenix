# Nullsafe Phoenix v2 - Runbook (Phase 1)

## Local Development Setup

### Prerequisites

**Required:**
- Python 3.11+
- Redis 6.0+
- Discord bot tokens (THREE tokens - one per agent from Discord Developer Portal)

**Install Python dependencies:**
```bash
pip install -r requirements.txt
```

## Starting the System

### 1. Start Redis

**Option A: Native Redis**
```bash
redis-server
```

**Option B: Docker**
```bash
docker run -d -p 6379:6379 --name phoenix-redis redis:latest
```

**Verify Redis is running:**
```bash
redis-cli ping
# Expected: PONG
```

### 2. Start Brain Service

**Terminal 1:**
```bash
cd services/brain
python main.py
```

**Expected output:**
```
============================================================
BRAIN CONFIGURATION:
  Identity dir: ./services/brain/identity/data
  Obsidian vault: Not configured
  Inference enabled: False
  Anthropic key: ✗ Not set
  OpenAI key: ✗ Not set
  DeepSeek key: ✗ Not set
============================================================
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

### 3. Start Relay Service

**Terminal 2:**
```bash
cd services/relay
python main.py
```

**Expected output:**
```
INFO:     Starting Relay service...
INFO:     Connected to Redis at redis://127.0.0.1:6379
INFO:     Brain client initialized for http://127.0.0.1:8001
INFO:     Queue drainer started
INFO:     Relay service started successfully
============================================================
RELAY CONFIGURATION:
  Brain URL: http://127.0.0.1:8001
  Redis URL: 127.0.0.1:6379
  Fast timeout: 5s
  Drainer timeout: 30s
  Drainer interval: 2s
  Max retries: 5
============================================================
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4. Start Discord Bots (THREE separate processes)

**IMPORTANT:** Phase 1 uses THREE separate Discord bot processes, one per agent.

#### Terminal 3: Drevan Bot

```bash
cd services/discord_bot
python bot.py --env .env.drevan
```

**Expected output:**
```
INFO:__main__: Loaded environment from .env.drevan
============================================================
DISCORD BOT CONFIGURATION:
  Agent ID: drevan
  Outbox key: phx:outbox:discord:drevan
  Relay URL: http://127.0.0.1:8000
  Redis URL: 127.0.0.1:6379
  Token: ✓ Set
============================================================
INFO:discord.client: logging in using static token
INFO:services.discord_bot.redis_client: Discord bot connected to Redis
INFO:services.discord_bot.relay_client: Relay client initialized
INFO:services.discord_bot.outbox_consumer: Outbox consumer started for phx:outbox:discord:drevan
INFO:services.discord_bot.bot: Phoenix bot setup complete
INFO:services.discord_bot.bot: Bot logged in as DrevanBot#1234
```

#### Terminal 4: Cypher Bot

```bash
cd services/discord_bot
python bot.py --env .env.cypher
```

**Expected output:**
```
INFO:__main__: Loaded environment from .env.cypher
============================================================
DISCORD BOT CONFIGURATION:
  Agent ID: cypher
  Outbox key: phx:outbox:discord:cypher
  Relay URL: http://127.0.0.1:8000
  Redis URL: 127.0.0.1:6379
  Token: ✓ Set
============================================================
INFO:services.discord_bot.bot: Bot logged in as CypherBot#5678
```

#### Terminal 5: Gaia Bot

```bash
cd services/discord_bot
python bot.py --env .env.gaia
```

**Expected output:**
```
INFO:__main__: Loaded environment from .env.gaia
============================================================
DISCORD BOT CONFIGURATION:
  Agent ID: gaia
  Outbox key: phx:outbox:discord:gaia
  Relay URL: http://127.0.0.1:8000
  Redis URL: 127.0.0.1:6379
  Token: ✓ Set
============================================================
INFO:services.discord_bot.bot: Bot logged in as GaiaBot#9012
```

### 5. Start Web UI (Optional)

**Terminal 6:**
```bash
cd services/web_ui
python main.py
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)
```

**Access:** Open browser to http://127.0.0.1:5000

## Acceptance Tests

### Test 1: Brain Service Health Check

**Verify Brain is online:**
```bash
curl http://127.0.0.1:8001/health
```

**Expected response:**
```json
{
  "status": "ok",
  "service": "brain",
  "version": "v2-day-one",
  "timestamp": "2026-01-31T12:00:00.000Z"
}
```

✅ **Pass criteria:** Status code 200, `status: "ok"`

---

### Test 2: Relay Service Status (Brain Online)

**Verify Relay reports Brain online:**
```bash
curl http://127.0.0.1:8000/status
```

**Expected response:**
```json
{
  "relay_status": "ok",
  "brain_status": "online",
  "brain_url": "http://127.0.0.1:8001",
  "redis_connected": true,
  "queue_lengths": {
    "incoming": 0,
    "inflight": 0,
    "deadletter": 0,
    "outbox": {
      "drevan": 0,
      "cypher": 0,
      "gaia": 0
    }
  },
  "drainer_running": true
}
```

✅ **Pass criteria:**
- `relay_status: "ok"`
- `brain_status: "online"`
- `redis_connected: true`
- `drainer_running: true`
- `outbox` is an object with three agent keys

---

### Test 3: Discord Message → Immediate Reply (Brain Online)

**Setup:**
1. Brain service running (Terminal 1)
2. Relay service running (Terminal 2)
3. At least one Discord bot running (Terminal 3, 4, or 5)

**Test steps:**
1. Send a message in Discord channel where the Cypher bot is present:
   ```
   Hello, Cypher!
   ```

2. **Expected bot reply** (within 1-2 seconds):
   ```
   [Cypher speaking]
   Identity anchor: Clarity over cleverness, always
   You said: "Hello, Cypher!"

   (Day One stub - no LLM inference yet)
   ```

**Verify in logs:**

**Terminal 4 (Cypher Bot):**
```
INFO:services.discord_bot.bot: Received message from User#1234 in channel 987654321: Hello, Cypher!...
INFO:services.discord_bot.relay_client: Relay ingested packet 550e8400-... (status: ok)
INFO:services.discord_bot.bot: Fast path success for packet 550e8400-..., sending reply
```

**Terminal 2 (Relay):**
```
INFO:services.relay.main: Ingest packet 550e8400-... from discord (dedupe check passed)
INFO:services.relay.brain_client: Brain processed packet 550e8400-... successfully
INFO:services.relay.redis_client: Enqueued to cypher outbox: 550e8400-...
```

**Terminal 1 (Brain):**
```
INFO:services.brain.agents.router: Routing packet 550e8400-... to agent cypher
INFO:services.brain.identity.loader: Loaded identity for cypher
INFO:services.brain.main: Returning reply for packet 550e8400-...
```

✅ **Pass criteria:**
- Discord bot receives reply within 2 seconds
- Reply contains agent identity anchor
- Logs show fast path success
- No errors in any terminal

---

### Test 4: Queue + Drainer (Brain Offline → Online)

**Test steps:**

1. **Stop Brain service** (CTRL+C in Terminal 1)

2. **Send Discord message:**
   ```
   This message should queue
   ```

3. **Expected bot reply** (immediate):
   ```
   ⏳ Queued (ID: 550e8400)
   ```

4. **Verify in Terminal 4 (Discord Bot):**
   ```
   INFO:services.discord_bot.relay_client: Relay ingested packet 550e8400-... (status: queued)
   INFO:services.discord_bot.bot: Packet 550e8400-... queued, sending acknowledgment
   ```

5. **Verify in Terminal 2 (Relay):**
   ```
   WARNING:services.relay.brain_client: Brain timeout for packet 550e8400-...
   INFO:services.relay.main: Fast path failed, enqueueing packet 550e8400-...
   INFO:services.relay.redis_client: Enqueued packet 550e8400-... to incoming queue
   ```

6. **Check queue length:**
   ```bash
   redis-cli LLEN phx:queue:incoming
   # Expected: 1
   ```

7. **Restart Brain service** (Terminal 1):
   ```bash
   cd services/brain
   python main.py
   ```

8. **Watch Terminal 2 (Relay drainer processes queue):**
   ```
   INFO:services.relay.drainer: Draining queue: found 1 packets
   INFO:services.relay.drainer: Processing packet 550e8400-... (attempt 1/5)
   INFO:services.relay.brain_client: Brain processed packet 550e8400-... successfully
   INFO:services.relay.drainer: Emitted reply to cypher outbox for packet 550e8400-...
   ```

9. **Watch Terminal 4 (Discord Bot outbox consumer):**
   ```
   INFO:services.discord_bot.outbox_consumer: Processing outbox event for packet 550e8400-...
   INFO:services.discord_bot.outbox_consumer: Successfully sent reply for packet 550e8400-...
   ```

10. **Expected Discord reply** (10-15 seconds after Brain restart):
    ```
    [Cypher speaking]
    Identity anchor: Clarity over cleverness, always
    You said: "This message should queue"

    (Day One stub - no LLM inference yet)
    ```

11. **Verify queues are empty:**
    ```bash
    redis-cli LLEN phx:queue:incoming
    # Expected: 0

    redis-cli LLEN phx:outbox:discord:cypher
    # Expected: 0 (processed)
    ```

✅ **Pass criteria:**
- Queued acknowledgment sent immediately (status="queued")
- Packet in `phx:queue:incoming` while Brain offline
- Drainer processes queue after Brain restart
- Reply delivered to Discord channel via per-agent outbox
- All queues empty after processing
- No duplicate replies

---

### Test 5: Multi-Agent Routing

**Test steps:**

1. **Ensure all three Discord bots are running** (Terminals 3, 4, 5)

2. **Send message to Drevan bot:**
   ```
   Hello Drevan
   ```

3. **Expected reply:**
   ```
   [Drevan speaking]
   Identity anchor: Memory is selective resonance, not perfect recall
   You said: "Hello Drevan"

   (Day One stub - no LLM inference yet)
   ```

4. **Send message to Gaia bot:**
   ```
   Hello Gaia
   ```

5. **Expected reply:**
   ```
   [Gaia speaking]
   Identity anchor: Patterns connect across domains
   You said: "Hello Gaia"

   (Day One stub - no LLM inference yet)
   ```

6. **Verify in Relay status:**
   ```bash
   curl http://127.0.0.1:8000/status
   ```

   **Check outbox structure shows all three agents:**
   ```json
   "outbox": {
     "drevan": 0,
     "cypher": 0,
     "gaia": 0
   }
   ```

✅ **Pass criteria:**
- Each bot responds with its own identity anchor
- Replies route to correct per-agent outboxes
- No cross-contamination between agents

---

### Test 6: Web UI

**Test steps:**

1. **Open Web UI:** http://127.0.0.1:5000

2. **Verify status display:**
   - Brain status: "online" (green)
   - Queue depths displayed
   - Outboxes show: "D:0 C:0 G:0"

3. **Select agent from dropdown** (Cypher, Drevan, or Gaia)

4. **Send test message:**
   ```
   Hello from Web UI
   ```

5. **Expected immediate reply:**
   ```
   [Cypher speaking]
   Identity anchor: Clarity over cleverness, always
   You said: "Hello from Web UI"

   (Day One stub - no LLM inference yet)
   ```

6. **Stop Brain, send another message:**
   - Should show "⏳ Queued (ID: ...)"
   - Queue depths should increase

✅ **Pass criteria:**
- Web UI displays system status correctly
- Agent selector works
- Messages send and receive replies
- Queued status displayed when Brain offline

---

### Test 7: Smoke Test Script

**Run comprehensive automated test:**

```bash
pwsh scripts/smoke_test.ps1
```

**Expected output:**
```
======================================
Phoenix v2 - Smoke Test
======================================

[Test 1] Checking Brain health...
  ✓ Brain is healthy

[Test 2] Checking Relay status...
  ✓ Relay sees Brain as online
  Queue depths:
    Incoming: 0
    Inflight: 0
    Deadletter: 0
    Outbox (drevan): 0
    Outbox (cypher): 0
    Outbox (gaia): 0

[Test 3] Sending packet with Brain online (fast path)...
  ✓ Fast path success: [Cypher speaking]...

[Test 4] Please STOP the Brain service now and press Enter...
[User presses Enter after stopping Brain]
[Test 4] Sending packet with Brain offline (queued)...
  ✓ Packet queued successfully

[Test 5] Verifying queue depth...
  ✓ Incoming queue has packets: 1

[Test 6] Please RESTART the Brain service now and press Enter...
[User presses Enter after restarting Brain]
[Test 6] Waiting for drainer to process queue (max 30s)...
  ✓ Queue drained successfully (took 4s)

[Test 7] Verifying reply in outbox...
  ✓ Reply in outbox (total: 1)
    Drevan: 0
    Cypher: 0
    Gaia: 1

[Test 8] Testing deduplication...
  ✓ Duplicate packet rejected correctly

======================================
Smoke Test Complete!
======================================
```

✅ **Pass criteria:** All 8 tests pass

---

## Troubleshooting

### Services Won't Start

**Error: Configuration validation failed**

```
ERROR:__main__: Configuration validation failed: DISCORD_TOKEN is required
```

**Solution:**
1. Check .env file has all required variables
2. For Discord bots, ensure using correct .env file with `--env` flag
3. Verify AGENT_ID is one of: drevan, cypher, gaia

---

**Error: IDENTITY_DIR does not exist**

```
ValueError: IDENTITY_DIR does not exist: ./services/brain/identity/data
```

**Solution:**
1. Verify you're in the correct directory
2. Check identity directory exists: `ls services/brain/identity/data`
3. Should contain: drevan.yaml, cypher.yaml, gaia.yaml

---

### Redis Connection Failed

**Error:**
```
redis.exceptions.ConnectionError: Error connecting to 127.0.0.1:6379
```

**Solution:**
1. Verify Redis is running:
   ```bash
   redis-cli ping
   # Expected: PONG
   ```
2. If not running, start Redis (see Step 1)
3. Check Redis URL in .env files uses 127.0.0.1:6379

---

### Brain Timeout

**Error in Relay logs:**
```
WARNING services.relay.brain_client: Brain timeout for packet ...
```

**Solution:**
1. Check Brain service is running (Terminal 1)
2. Verify Brain health: `curl http://127.0.0.1:8001/health`
3. Check Brain logs for errors
4. Increase timeout if needed: set `BRAIN_TIMEOUT_FAST=10` in Relay .env

---

### Discord Bot Not Responding

**Possible causes:**

1. **Wrong agent bot:**
   - Verify you're messaging the correct Discord bot
   - Drevan bot only responds in Drevan's channels
   - Each bot is separate

2. **DISCORD_TOKEN not set:**
   - Check .env.{agent} file has valid token
   - Each bot needs unique token

3. **Wrong outbox queue:**
   - Check bot config shows correct `OUTBOX_KEY`
   - Should match agent: `phx:outbox:discord:{agent}`

4. **Relay unreachable:**
   - Verify Relay is running: `curl http://127.0.0.1:8000/status`
   - Check RELAY_API_URL in bot .env file

---

### Queue Not Draining

**Check drainer status:**
```bash
curl http://127.0.0.1:8000/status
```

**Verify drainer is running:**
- `drainer_running: true`

**Check queue manually:**
```bash
redis-cli LLEN phx:queue:incoming
redis-cli LRANGE phx:queue:incoming 0 -1
```

**Check drainer interval:**
- Default: 2 seconds
- Increase if needed: set `DRAINER_INTERVAL=1` in Relay .env

**Restart Relay if needed:**
- CTRL+C in Terminal 2
- `python main.py`

---

### Messages Going to Wrong Agent

**Problem:** Cypher bot getting Drevan's messages

**Solution:**
1. Verify each bot is running with correct `--env` flag:
   ```bash
   python bot.py --env .env.drevan  # NOT .env.cypher
   ```

2. Check bot startup logs show correct `Agent ID`

3. Verify outbox keys in Relay status:
   ```bash
   curl http://127.0.0.1:8000/status | jq '.queue_lengths.outbox'
   ```

4. Check per-agent queue lengths:
   ```bash
   redis-cli LLEN phx:outbox:discord:drevan
   redis-cli LLEN phx:outbox:discord:cypher
   redis-cli LLEN phx:outbox:discord:gaia
   ```

---

### Duplicate Discord Messages

**Symptom:** Same reply sent multiple times

**Check dedupe:**
```bash
redis-cli SMEMBERS phx:discord:sent
```

**Should contain packet IDs of sent messages (24h TTL)**

**If duplicates occur:**
- Check Discord bot logs for "already sent (dedupe)"
- Verify outbox consumer is removing from inflight
- Check `phx:outbox:inflight` queue length:
  ```bash
  redis-cli LLEN phx:outbox:inflight
  ```

**Clear dedupe if needed (development only):**
```bash
redis-cli DEL phx:discord:sent
```

---

### Deadletter Queue Growing

**Check deadletter:**
```bash
redis-cli LLEN phx:queue:deadletter
```

**View deadletter events:**
```bash
redis-cli LRANGE phx:queue:deadletter 0 -1 | jq
```

**Common causes:**
- Brain repeatedly failing (check Brain logs)
- Invalid packet format
- Network issues between Relay and Brain

**Clear deadletter (after fixing root cause):**
```bash
redis-cli DEL phx:queue:deadletter
```

---

## Monitoring

### Queue Lengths

```bash
# Incoming queue (packets waiting for Brain)
redis-cli LLEN phx:queue:incoming

# Inflight (being processed by drainer)
redis-cli LLEN phx:queue:inflight

# Deadletter (failed after max retries)
redis-cli LLEN phx:queue:deadletter

# Per-agent outboxes (Phase 1)
redis-cli LLEN phx:outbox:discord:drevan
redis-cli LLEN phx:outbox:discord:cypher
redis-cli LLEN phx:outbox:discord:gaia

# Outbox inflight (being sent to Discord)
redis-cli LLEN phx:outbox:inflight
```

### Real-time Queue Monitoring

**Watch all queues:**
```bash
watch -n 1 'echo "Incoming: $(redis-cli LLEN phx:queue:incoming)"; echo "Inflight: $(redis-cli LLEN phx:queue:inflight)"; echo "Deadletter: $(redis-cli LLEN phx:queue:deadletter)"; echo "Outbox Drevan: $(redis-cli LLEN phx:outbox:discord:drevan)"; echo "Outbox Cypher: $(redis-cli LLEN phx:outbox:discord:cypher)"; echo "Outbox Gaia: $(redis-cli LLEN phx:outbox:discord:gaia)"'
```

### Dedupe Keys

```bash
# Ingress dedupe (24h TTL)
redis-cli KEYS "phx:dedupe:ingest:*"

# Outbox dedupe (24h TTL)
redis-cli KEYS "phx:dedupe:outbox:*"

# Discord sent (24h TTL)
redis-cli SMEMBERS phx:discord:sent
```

### Service Health

```bash
# Brain health
curl http://127.0.0.1:8001/health

# Relay status (shows everything)
curl http://127.0.0.1:8000/status | jq

# Web UI (if running)
curl http://127.0.0.1:5000 -I
```

---

## Configuration Tuning

### Increase Brain Timeout

Edit `services/relay/.env.relay`:
```bash
BRAIN_TIMEOUT_FAST=10        # Default: 5 seconds
BRAIN_TIMEOUT_DRAINER=60     # Default: 30 seconds
```

Restart Relay service.

### Increase Drainer Speed

Edit `services/relay/.env.relay`:
```bash
DRAINER_INTERVAL=1           # Default: 2 seconds (check queue every 1s)
```

Restart Relay service.

### Increase Retry Attempts

Edit `services/relay/.env.relay`:
```bash
MAX_RETRIES=10               # Default: 5 retries before deadletter
```

Restart Relay service.

### Change Dedupe TTL

Edit `services/relay/.env.relay`:
```bash
DEDUPE_TTL=43200            # Default: 86400 (24 hours) -> 12 hours
```

Restart Relay service.

---

## Stopping the System

**Graceful shutdown order:**

1. **Stop Discord Bots** (Terminals 3, 4, 5): CTRL+C
2. **Stop Web UI** (Terminal 6, if running): CTRL+C
3. **Stop Relay** (Terminal 2): CTRL+C
4. **Stop Brain** (Terminal 1): CTRL+C
5. **Stop Redis** (if using Docker):
   ```bash
   docker stop phoenix-redis
   ```

---

## Running Tests

```bash
# All tests (unit + integration)
pytest

# Integration tests only
pytest integration_tests/ -v

# Specific service
pytest services/brain/tests/ -v
pytest services/relay/tests/ -v
pytest services/discord_bot/tests/ -v

# With coverage
pytest --cov=services --cov=shared

# Specific test file
pytest services/relay/tests/test_relay.py::TestRedisClient::test_enqueue_outbox -v
```

---

## Quick Reset

**Clear all Redis data:**
```bash
redis-cli FLUSHALL
```

**Warning:** This clears ALL data including:
- Queues (incoming, inflight, deadletter)
- Per-agent outboxes (drevan, cypher, gaia)
- Dedupe keys
- Thread routing mappings

Use only for development/testing.

**Restart all services after reset.**

---

## Production Deployment Notes

### VPS Setup (Relay + Redis)

**Relay:**
- Always-on VPS service
- Redis on same VPS for low latency
- Configure `BRAIN_SERVICE_URL` to point to workstation

**Example production .env.relay:**
```bash
BRAIN_SERVICE_URL=https://brain.yourworkstation.com:8001
REDIS_URL=redis://127.0.0.1:6379
BRAIN_TIMEOUT_FAST=10
DRAINER_INTERVAL=5
```

### Workstation Setup (Brain)

**Brain:**
- Runs on local workstation (may go offline)
- No Redis dependency
- Configure firewall to allow Relay connections

**Example production .env.brain:**
```bash
INFERENCE_ENABLED=true
ANTHROPIC_API_KEY=sk-ant-...
OBSIDIAN_VAULT_PATH=/Users/you/Documents/Vault
```

### Discord Bots

**Can run on VPS or workstation:**
- Prefer VPS for 24/7 availability
- Each bot is independent process
- Use systemd/supervisor for auto-restart

**Systemd example:**
```ini
[Unit]
Description=Phoenix Cypher Bot
After=network.target

[Service]
Type=simple
User=phoenix
WorkingDirectory=/opt/phoenix/services/discord_bot
ExecStart=/usr/bin/python3 bot.py --env .env.cypher
Restart=always

[Install]
WantedBy=multi-user.target
```

---

**Phase 1 system ready for production deployment!**
