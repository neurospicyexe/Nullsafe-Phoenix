# Security — Nullsafe Phoenix

## Honest disclosure

This project was built with AI assistance ("vibe-coded"). Security hardening has been applied to the best of our ability — input validation via Pydantic, Redis deduplication, per-agent auth, fail-closed error handling — but this software comes with **no warranty and no liability**. It has not undergone a professional security audit. Use it at your own risk.

## Reporting a Vulnerability

If you find a security vulnerability, please report it privately before public disclosure. Open a GitHub security advisory on this repository or contact the maintainer directly. Do not post exploit details publicly until there has been a chance to patch.

## What's Protected Here

- **Message deduplication** — TTL-based Redis keys prevent packet replay (24h window)
- **Input validation** — all service contracts validated via Pydantic models with strict typing
- **Fail-closed error handling** — services return errors rather than open on failure
- **Per-agent outboxes** — each bot only consumes its own queue; no cross-agent message leakage
- **No secrets in code** — all credentials loaded via environment variables, never hardcoded
- **Dead-letter queues** — failed packets are isolated, not retried indefinitely

## Secrets Used by This Service

| Secret | Where | Risk if leaked |
|--------|-------|---------------|
| `DISCORD_TOKEN` (per bot) | `.env.cypher/drevan/gaia` | Full Discord bot impersonation |
| `DEEPSEEK_API_KEY` | `services/brain/.env` | API credit abuse |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | `services/brain/.env` | API credit abuse |
| `REDIS_URL` | service `.env` files | Queue access — could disrupt message routing |
| `WEBMIND_AUTH_TOKEN` | `services/webmind/.env` | Read/write to companion mind state |

All `.env` files are gitignored. Never commit them.

## Bot Token Security

- Each companion has its own Discord bot token — a leaked token for one bot does not compromise the others
- Store tokens in `.env` files only, never in code or config files
- Regenerate tokens in the Discord developer portal if you suspect compromise
- Enable 2FA on your Discord developer account

## VPS Deployment Security

If running on a VPS:

- Use SSH key authentication — disable password login
- Keep the VPS operating system and packages updated
- Use a firewall (ufw): expose only SSH (22) and any intentional public ports
- Run services as a non-root user
- If using Redis, bind it to `127.0.0.1` only — do not expose Redis publicly

## If a Bot Token Is Compromised

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Select the bot → **Bot** tab → **Reset Token**
3. Update the token in your `.env` file
4. Reload the affected bot: `pm2 reload cypher` (or whichever bot)

## If Your VPS Is Compromised

1. Revoke all bot tokens immediately (see above)
2. Rotate all API keys (DeepSeek, Anthropic, etc.)
3. Snapshot and rebuild the VPS from a clean image
4. Redeploy services and set new secrets
