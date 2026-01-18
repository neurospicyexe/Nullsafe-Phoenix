# Nullsafe Phoenix v2 - Runbook

## Local Development Setup

### Prerequisites

**Required:**
- Python 3.11+
- Redis 6.0+
- Discord bot token (from Discord Developer Portal)

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
INFO:     Connected to Redis at redis://localhost:6379
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started queue drainer background task
```

### 4. Start Discord Bot

**Terminal 3:**
```bash
# Set your Discord bot token
export DISCORD_TOKEN=your_bot_token_here

# Or on Windows
set DISCORD_TOKEN=your_bot_token_here

cd services/discord_bot
python bot.py
```

**Expected output:**
```
INFO discord.client: logging in using static token
INFO services.discord_bot.bot: Setting up Phoenix bot...
INFO services.discord_bot.redis_client: Discord bot connected to Redis at redis://localhost:6379
INFO services.discord_bot.relay_client: Relay client initialized for http://localhost:8000
INFO services.discord_bot.outbox_consumer: Outbox consumer started
INFO services.discord_bot.bot: Phoenix bot setup complete
INFO services.discord_bot.bot: Bot logged in as PhoenixBot#1234 (ID: 123456789)
INFO services.discord_bot.bot: Connected to 1 guilds
```

## Acceptance Tests

### Test 1: Brain Service Health Check

**Verify Brain is online:**
```bash
curl http://localhost:8001/health
```

**Expected response:**
```json
{
  "status": "ok",
  "service": "brain",
  "timestamp": "2026-01-18T12:00:00.000Z"
}
```

✅ **Pass criteria:** Status code 200, `status: "ok"`

---

### Test 2: Relay Service Status (Brain Online)

**Verify Relay reports Brain online:**
```bash
curl http://localhost:8000/status
```

**Expected response:**
```json
{
  "relay_status": "ok",
  "brain_status": "online",
  "brain_url": "http://localhost:8001",
  "redis_connected": true,
  "queue_lengths": {
    "incoming": 0,
    "inflight": 0,
    "deadletter": 0,
    "outbox": 0
  },
  "drainer_running": true
}
```

✅ **Pass criteria:**
- `relay_status: "ok"`
- `brain_status: "online"`
- `redis_connected: true`
- `drainer_running: true`

---

### Test 3: Discord Message → Immediate Reply (Brain Online)

**Setup:**
1. Brain service running (Terminal 1)
2. Relay service running (Terminal 2)
3. Discord bot running (Terminal 3)

**Test steps:**
1. Send a message in Discord channel where bot is present:
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

**Terminal 3 (Discord Bot):**
```
INFO services.discord_bot.bot: Received message from User#1234 in channel 987654321: Hello, Cypher!...
INFO services.discord_bot.bot: Constructed ThoughtPacket 550e8400-e29b-41d4-a716-446655440000 for agent cypher
INFO services.discord_bot.relay_client: Relay ingested packet 550e8400-... (status: ok)
INFO services.discord_bot.bot: Fast path success for packet 550e8400-..., sending reply
```

**Terminal 2 (Relay):**
```
INFO services.relay.main: Ingest packet 550e8400-... from discord (dedupe check passed)
INFO services.relay.main: Fast path to Brain for packet 550e8400-...
INFO services.relay.brain_client: Brain processed packet 550e8400-... successfully
INFO services.relay.main: Fast path success, returning reply
```

**Terminal 1 (Brain):**
```
INFO services.brain.main: Processing packet 550e8400-... for agent cypher
INFO services.brain.thread_router: Thread 987654321 -> agent cypher
INFO services.brain.identity: Loaded identity for cypher (version: 1.0)
INFO services.brain.main: Returning reply for packet 550e8400-...
```

✅ **Pass criteria:**
- Discord bot receives reply within 2 seconds
- Reply contains agent identity anchor
- Logs show "Fast path success"
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

4. **Verify in Terminal 3 (Discord Bot):**
   ```
   INFO services.discord_bot.relay_client: Relay ingested packet 550e8400-... (status: queued)
   INFO services.discord_bot.bot: Packet 550e8400-... queued, sending acknowledgment
   ```

5. **Verify in Terminal 2 (Relay):**
   ```
   WARNING services.relay.brain_client: Brain timeout for packet 550e8400-...
   INFO services.relay.main: Fast path failed, enqueueing packet 550e8400-...
   INFO services.relay.redis_client: Enqueued packet 550e8400-... to incoming queue
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
   INFO services.relay.drainer: Draining queue: found 1 packets
   INFO services.relay.drainer: Processing packet 550e8400-... (attempt 1/5)
   INFO services.relay.brain_client: Brain processed packet 550e8400-... successfully
   INFO services.relay.drainer: Emitting reply to outbox for packet 550e8400-...
   INFO services.relay.redis_client: Emitted packet 550e8400-... to outbox
   ```

9. **Watch Terminal 3 (Discord Bot outbox consumer):**
   ```
   INFO services.discord_bot.outbox_consumer: Sending reply for packet 550e8400-... to channel 987654321
   INFO services.discord_bot.outbox_consumer: Successfully sent reply for packet 550e8400-...
   INFO services.discord_bot.redis_client: Marked packet 550e8400-... as sent to Discord
   ```

10. **Expected Discord reply** (10-15 seconds after Brain restart):
    ```
    [Cypher speaking]
    Identity anchor: Clarity over cleverness, always
    You said: "This message should queue"

    (Day One stub - no LLM inference yet)
    ```

11. **Verify queue is empty:**
    ```bash
    redis-cli LLEN phx:queue:incoming
    # Expected: 0

    redis-cli LLEN phx:outbox:discord
    # Expected: 0 (processed)
    ```

✅ **Pass criteria:**
- Queued acknowledgment sent immediately (status="queued")
- Packet in `phx:queue:incoming` while Brain offline
- Drainer processes queue after Brain restart
- Reply delivered to Discord channel via outbox
- All queues empty after processing
- No duplicate replies

---

### Test 5: Obsidian Write Tool

**Note:** The Obsidian write tool is optional for Day One. This test validates the Brain's ability to handle tool calls if implemented.

**Test with curl:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{
    "packet_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-01-18T12:00:00.000Z",
    "source": "webui",
    "user_id": "webui:test",
    "thread_id": "test-thread-123",
    "agent_id": "cypher",
    "message": "Write a note about testing to notes/test.md",
    "metadata": {}
  }'
```

**Expected response (Day One stub):**
```json
{
  "packet_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_id": "cypher",
  "status": "ok",
  "reply_text": "[Cypher speaking]\nIdentity anchor: Clarity over cleverness, always\nYou said: \"Write a note about testing to notes/test.md\"\n\n(Day One stub - no LLM inference yet)",
  "trace": {
    "repro_stamp": "cypher@1.0|2026-01-18T12:00:00.000Z"
  },
  "writes": null
}
```

**Expected logs (Terminal 1):**
```
INFO services.brain.main: Processing packet 550e8400-... for agent cypher
INFO services.brain.identity: Loaded identity for cypher (version: 1.0)
INFO services.brain.main: Day One stub - no actual LLM call or tool execution
INFO services.brain.main: Returning reply for packet 550e8400-...
```

✅ **Pass criteria (Day One):**
- Brain accepts packet with tool request
- Returns status="ok"
- Logs mention "Day One stub"
- No crashes or errors
- `writes: null` (not implemented yet)

**Future implementation:**
- Brain will parse message for tool requests
- Execute obsidian write
- Return `writes: [{"path": "notes/test.md", "content": "..."}]`

---

## Troubleshooting

### Redis Connection Failed

**Error:**
```
redis.exceptions.ConnectionError: Error 10061 connecting to localhost:6379
```

**Solution:**
1. Verify Redis is running:
   ```bash
   redis-cli ping
   ```
2. If not running, start Redis (see Step 1)

### Brain Timeout

**Error in Relay logs:**
```
WARNING services.relay.brain_client: Brain timeout for packet ...
```

**Solution:**
1. Check Brain service is running (Terminal 1)
2. Verify Brain health: `curl http://localhost:8001/health`
3. Check Brain logs for errors

### Discord Bot Not Responding

**Possible causes:**

1. **Bot not in channel:**
   - Invite bot to server with proper permissions
   - Bot needs "Send Messages" and "Read Message Content" permissions

2. **DISCORD_TOKEN not set:**
   ```bash
   export DISCORD_TOKEN=your_token_here
   ```

3. **Relay unreachable:**
   - Verify Relay is running: `curl http://localhost:8000/status`

4. **Check bot logs** (Terminal 3) for errors

### Queue Not Draining

**Check drainer status:**
```bash
curl http://localhost:8000/status
```

**Verify drainer is running:**
- `drainer_running: true`

**Check queue manually:**
```bash
redis-cli LLEN phx:queue:incoming
redis-cli LRANGE phx:queue:incoming 0 -1
```

**Restart Relay if needed:**
- CTRL+C in Terminal 2
- `python main.py`

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
- Check `phx:outbox:inflight` queue length

### Deadletter Queue Growing

**Check deadletter:**
```bash
redis-cli LLEN phx:queue:deadletter
```

**View deadletter events:**
```bash
redis-cli LRANGE phx:queue:deadletter 0 -1
```

**Common causes:**
- Brain repeatedly failing (check Brain logs)
- Invalid packet format
- Network issues

**Clear deadletter (after fixing root cause):**
```bash
redis-cli DEL phx:queue:deadletter
```

## Monitoring

### Queue Lengths

```bash
# Incoming queue (packets waiting for Brain)
redis-cli LLEN phx:queue:incoming

# Inflight (being processed by drainer)
redis-cli LLEN phx:queue:inflight

# Deadletter (failed after max retries)
redis-cli LLEN phx:queue:deadletter

# Outbox (replies waiting for Discord)
redis-cli LLEN phx:outbox:discord

# Outbox inflight
redis-cli LLEN phx:outbox:inflight
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

### Thread Routing

```bash
# View all thread mappings
redis-cli KEYS "phx:thread:*"

# View specific thread
redis-cli GET "phx:thread:987654321"
# Returns: cypher (or other agent)
```

## Stopping the System

1. **Stop Discord Bot** (Terminal 3): CTRL+C
2. **Stop Relay** (Terminal 2): CTRL+C
3. **Stop Brain** (Terminal 1): CTRL+C
4. **Stop Redis** (if using Docker):
   ```bash
   docker stop phoenix-redis
   ```

## Running Tests

```bash
# All tests (unit + integration)
python -m pytest

# Integration tests only
python -m pytest integration_tests/ -v

# Specific service
python -m pytest services/brain/tests/ -v
python -m pytest services/relay/tests/ -v
python -m pytest services/discord_bot/tests/ -v

# With coverage
python -m pytest --cov=services --cov=shared
```

## Quick Reset

**Clear all Redis data:**
```bash
redis-cli FLUSHALL
```

**Warning:** This clears ALL data including:
- Queues (incoming, inflight, deadletter, outbox)
- Dedupe keys
- Thread routing mappings

Use only for development/testing.

---

**System ready for production deployment!**
