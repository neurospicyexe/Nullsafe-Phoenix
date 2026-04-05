# Nullsafe Phoenix - Quick Start Guide

This guide contains all commands needed to run the Nullsafe Phoenix v2 system.

## Prerequisites

- Python 3.11+
- Redis (Docker or local installation)
- Dependencies installed in each service directory

## Service Startup Order

Services must be started in this order:
1. Redis
2. Relay Service
3. Brain Service
4. Discord Bot (when ready)

---

## 1. Start Redis (Docker)

**Terminal 1: Redis**

```powershell
# Start Redis container on port 6380
docker start phx-redis

# If container doesn't exist, create it:
# docker run -d --name phx-redis -p 6380:6379 redis:7

# Verify Redis is running
docker ps | findstr phx-redis
```

**Alternative: Local Redis**
```powershell
redis-server
```

---

## 2. Start Relay Service

**Terminal 2: Relay**

```powershell
cd C:\dev\"Nullsafe Phoenix"\services\relay
$env:PYTHONPATH="C:\dev\Nullsafe Phoenix"
$env:REDIS_URL="redis://localhost:6380"
python main.py
```

Expected output:
```
INFO: Started server process
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## 3. Start Brain Service

**Terminal 3: Brain**

```powershell
cd C:\dev\"Nullsafe Phoenix"\services\brain
$env:PYTHONPATH="C:\dev\Nullsafe Phoenix"
python main.py
```

Expected output:
```
INFO: Started server process
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8001
```

---

## 4. Start Discord Bot (Future)

**Terminal 4: Discord Bot**

```powershell
cd C:\dev\"Nullsafe Phoenix"\services\discord_bot
$env:PYTHONPATH="C:\dev\Nullsafe Phoenix"
$env:DISCORD_TOKEN="your_token_here"
$env:REDIS_URL="redis://localhost:6380"
python bot.py
```

---

## Health Checks

Once all services are running, verify they're healthy:

```powershell
# Check Relay service
curl http://localhost:8000/health

# Check Relay status (shows Brain connection and queue depths)
curl http://localhost:8000/status

# Check Brain service
curl http://localhost:8001/health
```

Expected `/status` response:
```json
{
  "brain_status": "online",
  "queue_lengths": {
    "incoming": 0,
    "inflight": 0,
    "deadletter": 0,
    "outbox": 0
  },
  "timestamp": "2026-01-30T..."
}
```

---

## Redis Queue Inspection

```powershell
# Check queue lengths
redis-cli -p 6380 LLEN phx:queue:incoming
redis-cli -p 6380 LLEN phx:queue:inflight
redis-cli -p 6380 LLEN phx:queue:deadletter
redis-cli -p 6380 LLEN phx:outbox:discord

# View all Phoenix keys
redis-cli -p 6380 KEYS "phx:*"

# Clear all data (DANGER - development only!)
redis-cli -p 6380 FLUSHALL
```

---

## Stopping Services

Press `Ctrl+C` in each terminal to gracefully stop services.

Stop in reverse order:
1. Discord Bot
2. Brain Service
3. Relay Service
4. Redis (optional - can leave running)

```powershell
# Stop Redis container (optional)
docker stop phx-redis
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'shared'"

**Solution:** Set PYTHONPATH to project root:
```powershell
$env:PYTHONPATH="C:\dev\Nullsafe Phoenix"
```

### "Connection refused" when connecting to Redis

**Solutions:**
1. Ensure Redis is running: `docker ps`
2. Check port mapping: Redis container should map 6380→6379
3. Verify REDIS_URL: `$env:REDIS_URL="redis://localhost:6380"`

### "Connection refused" when Relay tries to reach Brain

**Solutions:**
1. Ensure Brain service is running on port 8001
2. Check Brain health: `curl http://localhost:8001/health`
3. Check firewall settings

### Services log too much

Both services now have access logging disabled. If you see excessive logs:
- Restart the service (changes only apply after restart)
- Check that `access_log=False` is in uvicorn.run() calls

---

## Service Ports

| Service | Port | URL |
|---------|------|-----|
| Redis | 6380 | redis://localhost:6380 |
| Relay | 8000 | http://localhost:8000 |
| Brain | 8001 | http://localhost:8001 |

---

## Environment Files

- Relay: `services/relay/.env.relay`
- Brain: `services/brain/.env.brain`
- Discord Bot: `services/discord_bot/.env.discord`

Current configuration:
- `REDIS_URL=redis://localhost:6380` (Relay, Discord Bot)
- `BRAIN_SERVICE_URL=http://localhost:8001` (Relay)
- API keys configured in `.env.brain` (optional for Day One)

---

## Quick Test

Once all services are running, test the full stack with a curl command:

```powershell
# Send a test ThoughtPacket to Relay
curl -X POST http://localhost:8000/ingest `
  -H "Content-Type: application/json" `
  -d '{
    "packet_id": "test-123",
    "timestamp": "2026-01-30T12:00:00Z",
    "source": "manual-test",
    "user_id": "user-123",
    "thread_id": "thread-456",
    "agent_id": "drevan",
    "message": "Hello, Drevan!",
    "metadata": {}
  }'
```

Expected response will include agent reply with status "ok" and a stub response.

---

## Notes

- **Day One Status:** System returns stub replies (no actual LLM calls yet)
- **Offline Mode:** Brain can go offline; Relay will queue messages
- **Crash-Safe:** All queues use atomic Redis operations
- **Deduplication:** 24-hour TTL prevents duplicate processing

For full architecture details, see [CLAUDE.md](CLAUDE.md)
