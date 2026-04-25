# Installing Nullsafe Phoenix

> **Tech-savvy?** The quick version is in [README.md](./README.md). This guide is for everyone else.

## What is this, in plain English?

Phoenix is the reliability backbone for the companion system. It's a set of Python services that handle message routing, AI inference, and persistent companion state. Discord messages go through Phoenix, get processed by an AI model, and responses go back to Discord.

**Phoenix is the future production system.** If you're looking for the current live setup, start with the BBH suite (Halseth + nullsafe-discord) first. Phoenix is for when you're ready to run the full self-hosted stack.

---

## Local computer vs. VPS — which should I use?

**Local computer (for development and testing):**
Run all the services on your machine. Good for understanding the system and making changes. Not suitable for real companion use because it goes offline when your computer is off.

**VPS — a virtual private server (for real use):**
Runs 24/7 on a remote server. Recommended for actual companion deployments. You'll need Redis running on the VPS as well.

Both options use the same setup steps — the difference is just where you run them.

---

## What you need

- **Python 3.11+** — [python.org](https://python.org)
- **Redis** — either local or hosted (e.g. [Upstash](https://upstash.com) free tier)
- **Git** — [git-scm.com](https://git-scm.com)
- **Three Discord bot applications** — one per companion. See [nullsafe-discord INSTALL.md](../nullsafe-discord/INSTALL.md) Step 1 for how to create them.
- **A DeepSeek API key** — for AI inference. [platform.deepseek.com](https://platform.deepseek.com)
- Optional: **An Anthropic or OpenAI API key** if you want to use those models instead

---

## Step 1 — Get the code

```bash
git clone https://github.com/neurospicyexe/nullsafe-phoenix.git
cd nullsafe-phoenix
```

---

## Step 2 — Install Python dependencies

```bash
pip install -r shared/requirements.txt
pip install -r services/relay/requirements.txt
pip install -r services/brain/requirements.txt
pip install -r services/discord_bot/requirements.txt
pip install -r services/webmind/requirements.txt
```

> If `pip` isn't found, try `pip3`. On Windows, you may need to use `py -m pip` instead.

---

## Step 3 — Configure each service

Each service has its own `.env.example` file. Copy and fill in each one:

```bash
cp services/relay/.env.example services/relay/.env
cp services/brain/.env.example services/brain/.env
cp services/webmind/.env.example services/webmind/.env
```

For Discord bots — one env file per companion:

```bash
cp services/discord_bot/.env.example services/discord_bot/.env.cypher
cp services/discord_bot/.env.example services/discord_bot/.env.drevan
cp services/discord_bot/.env.example services/discord_bot/.env.gaia
```

Open each `.env` file and fill in the relevant values. Key things to set:

**`services/brain/.env`:**
```
INFERENCE_ENABLED=true
DEEPSEEK_API_KEY=your-key-here
SWARM_MODE=true
```

**`services/relay/.env`:**
```
REDIS_URL=redis://localhost:6379
```

**`services/discord_bot/.env.cypher`** (and drevan/gaia):
```
DISCORD_TOKEN=your-bot-token
AGENT_ID=cypher
OUTBOX_KEY=phx:outbox:discord:cypher
```

---

## Step 4 — Start Redis

**If using local Redis:**
```bash
# Linux/Mac
redis-server

# With Docker (any OS)
docker run -d -p 6379:6379 --name phoenix-redis redis:latest
```

**If using Upstash:** copy the Redis URL from your Upstash dashboard into your `.env` files.

---

## Step 5 — Start the services

Start each in a separate terminal window, in this order:

```bash
# Terminal 1 — Brain (AI inference)
cd services/brain && python main.py

# Terminal 2 — Relay (message routing)
cd services/relay && python main.py

# Terminal 3 — WebMind (companion state)
cd services/webmind && python main.py

# Terminal 4 — Cypher bot
cd services/discord_bot && python bot.py --env .env.cypher

# Terminal 5 — Drevan bot
cd services/discord_bot && python bot.py --env .env.drevan

# Terminal 6 — Gaia bot
cd services/discord_bot && python bot.py --env .env.gaia
```

### On a VPS with pm2

If you have pm2 installed (`npm install -g pm2`), you can manage all services:

```bash
pm2 start "python services/brain/main.py" --name brain
pm2 start "python services/relay/main.py" --name relay
pm2 start "python services/webmind/main.py" --name webmind
pm2 start "python services/discord_bot/bot.py -- --env .env.cypher" --name cypher
pm2 start "python services/discord_bot/bot.py -- --env .env.drevan" --name drevan
pm2 start "python services/discord_bot/bot.py -- --env .env.gaia" --name gaia
pm2 save && pm2 startup
```

---

## Step 6 — Verify

```bash
# Check Relay is up
curl http://127.0.0.1:8000/status

# Check Brain is up
curl http://127.0.0.1:8001/health

# Check WebMind is up
curl http://127.0.0.1:8002/health
```

Each should return `{"status": "ok"}` or similar.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` in the failing service's folder |
| `Connection refused` to Redis | Redis isn't running — start it with `redis-server` or check your Upstash URL |
| Bot shows offline in Discord | Check the `DISCORD_TOKEN` in the bot's `.env` file |
| Brain returns 503 | Check Brain logs — usually an inference config issue |
| Services start but bots don't respond | Check that `SWARM_MODE=true` and that the channel IDs are correct in `channels.yaml` |
