# Phoenix v2 - Web UI

Thin web client for Nullsafe Phoenix v2. Built with FastAPI + Jinja templates + vanilla JavaScript.

## Architecture

The Web UI is a **thin client** that:
- ✅ Only talks to the Relay service (never directly to Brain)
- ✅ Does NOT implement RAG, memory graphs, tools, or autonomy panels
- ✅ Provides a minimal, stable interface for chat and status monitoring
- ✅ Built with FastAPI (server) + Jinja2 (templates) + vanilla JavaScript (client)

## Features

### Status Panel (Left Sidebar)
- Real-time system status (polls every 2 seconds)
- Relay health (status, Redis connection, drainer state)
- Brain status (online/offline)
- Queue lengths (incoming, inflight, outbox, deadletter)

### Chat Panel (Main Area)
- Agent selector: Drevan | Cypher | Gaia
- Lane selector (optional): Immersion | Praxis | Translation | Research
- Thread ID: Auto-generated, stored in localStorage for session persistence
- Message history with packet IDs
- Real-time responses via Relay `/ingest` endpoint

## Prerequisites

- Python 3.11+
- Running Relay service (see `../relay/`)

## Installation

```bash
cd services/web_ui
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Set the Relay API URL:

```bash
# For local development
export RELAY_API_URL=http://localhost:8000

# Or on Windows
set RELAY_API_URL=http://localhost:8000

# For production (VPS)
export RELAY_API_URL=https://your-vps.com/relay
```

**Optional:**
```bash
# Change web UI port (default: 3000)
export WEB_UI_PORT=3000
```

## Running Locally

### Development Mode

```bash
# Set environment variable
export RELAY_API_URL=http://localhost:8000

# Run the server
python main.py
```

The app will be available at **http://localhost:3000**

### Using uvicorn directly

```bash
export RELAY_API_URL=http://localhost:8000
uvicorn main:app --host 0.0.0.0 --port 3000 --reload
```

## Usage

### 1. Start Required Services

Before using the Web UI, ensure these services are running:

**Redis:**
```bash
redis-server
```

**Brain Service:**
```bash
cd services/brain
python main.py
# Runs on http://localhost:8001
```

**Relay Service:**
```bash
cd services/relay
python main.py
# Runs on http://localhost:8000
```

### 2. Access Web UI

Open your browser to **http://localhost:3000**

### 3. Using the Chat

1. **Select Agent**: Choose Drevan, Cypher, or Gaia from the dropdown
2. **Select Lane** (optional): Choose a processing lane or leave as Default
3. **Send Message**: Type your message and click Send (or press Enter)
4. **View Responses**:
   - Fast path (Brain online): Reply appears immediately
   - Queued (Brain offline): Shows "⏳ Queued (ID: abc123)"

### 4. Monitor System Status

The left panel shows real-time status:
- **Relay Status**: Should show "ok" with Redis connected and drainer running
- **Brain Status**: Shows "online" when Brain service is reachable
- **Queue Lengths**: Monitor message queues and deadletter queue

## How It Works

### Message Flow

1. **User sends message** → Browser JS constructs ThoughtPacket
2. **POST to Relay** → `/ingest` endpoint
3. **Relay response**:
   - `status: "ok"` → Brain processed immediately, reply shown
   - `status: "queued"` → Brain offline, message queued for later
4. **Display result** → User message + agent reply (or queued notice)

### ThoughtPacket Format

```javascript
{
  packet_id: "550e8400-e29b-41d4-a716-446655440000",  // UUID v4
  timestamp: "2026-01-18T12:00:00.000Z",              // ISO-8601
  source: "webui",
  user_id: "webui:<session_id>",                     // Browser session
  thread_id: "<session_id>",                          // Persistent thread
  agent_id: "cypher",                                 // Selected agent
  message: "Hello, Cypher!",                          // User input
  metadata: {
    platform: "webui",
    lane: "immersion"                                 // Optional
  }
}
```

### Session Management

- **Thread ID**: Generated once per browser, stored in `localStorage` as `phoenix_session_id`
- **Persistent**: Same thread ID across page reloads
- **Reset**: Clear localStorage to start a new thread

## Project Structure

```
services/web_ui/
├── main.py                      # FastAPI server
├── requirements.txt             # Python dependencies
├── templates/
│   └── index.html              # Main page template
├── static/
│   ├── styles.css              # CSS styles
│   └── app.js                  # Client-side JavaScript
└── README.md                   # This file
```

## API Endpoints

### Web UI Endpoints

**GET /**
Serves the main chat page (Jinja template)

**GET /health**
Health check for Web UI service

```json
{
  "status": "ok",
  "service": "web_ui",
  "relay_url": "http://localhost:8000"
}
```

### Relay Endpoints Used

**GET /status**
Returns system status (polled every 2s by JavaScript)

**POST /ingest**
Ingests ThoughtPacket and returns AgentReply

## Troubleshooting

### "Failed to fetch status"

**Problem:** Cannot connect to Relay service

**Solutions:**
1. Verify Relay is running: `curl http://localhost:8000/health`
2. Check `RELAY_API_URL` environment variable
3. Ensure Relay port (8000) is not blocked by firewall

### "Brain Status: offline"

**Problem:** Relay cannot reach Brain service

**Solutions:**
1. Start Brain service: `cd services/brain && python main.py`
2. Verify Brain health: `curl http://localhost:8001/health`
3. Check Brain logs for errors

### Messages showing "⏳ Queued"

**Status:** Normal behavior when Brain is offline

**What happens:**
1. Message is stored in `phx:queue:incoming`
2. When Brain comes online, drainer processes queue
3. Reply delivered via Discord bot outbox (not back to Web UI for Day One)

**Note:** Web UI does not currently poll for queued message replies. This is a Day One limitation.

### CORS Errors

If Web UI and Relay are on different domains/ports, you may see CORS errors.

**Solution:** Add CORS middleware to Relay service (for development):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Keyboard Shortcuts

- **Enter**: Send message
- **Shift + Enter**: New line in message input

## Browser Support

- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- Mobile browsers: ⚠️ Works but not optimized

## Production Deployment

### Using Systemd

Create `/etc/systemd/system/phoenix-webui.service`:

```ini
[Unit]
Description=Phoenix Web UI
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/phoenix/services/web_ui
Environment="RELAY_API_URL=https://your-vps.com/relay"
Environment="WEB_UI_PORT=3000"
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable phoenix-webui
sudo systemctl start phoenix-webui
```

### Using PM2 (Node.js Process Manager)

While the Web UI is Python-based, you can still use PM2:

```bash
pm2 start main.py --name phoenix-webui --interpreter python3
pm2 save
pm2 startup
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Development Notes

### Adding New Features

The Web UI is intentionally minimal. For Day One, it does NOT include:
- ❌ RAG (Retrieval Augmented Generation)
- ❌ Memory graphs
- ❌ Tool panels
- ❌ Autonomy controls
- ❌ Real-time message updates from queue

These features should be added to the Brain service, not the Web UI.

### Styling

Uses vanilla CSS with CSS variables for theming. The design is minimal and functional.

Dark mode automatically follows browser preference (`prefers-color-scheme: dark`).

### JavaScript

Pure vanilla JavaScript (no frameworks). All code in `static/app.js`.

The UUID generator is a simple client-side implementation for Day One. For production, consider using a proper UUID library.

## Testing

### Manual Testing

1. Start all services (Redis, Brain, Relay, Web UI)
2. Open http://localhost:3000
3. Send a message
4. Verify reply appears
5. Stop Brain service
6. Send another message
7. Verify "Queued" appears
8. Restart Brain
9. Check status panel updates

### Health Check

```bash
curl http://localhost:3000/health
```

Expected:
```json
{
  "status": "ok",
  "service": "web_ui",
  "relay_url": "http://localhost:8000"
}
```

## Differences from Next.js Version

This FastAPI version is simpler:
- ✅ No Node.js dependencies
- ✅ No build step required
- ✅ Server-side template rendering (Jinja2)
- ✅ Vanilla JavaScript (no React)
- ✅ Smaller footprint (~10KB vs ~500KB)
- ✅ Easier to deploy (single Python process)

## License

Part of Nullsafe Phoenix v2 system.

---

**Status:** ✅ Ready for local development and production deployment
**Version:** v2-day-one
