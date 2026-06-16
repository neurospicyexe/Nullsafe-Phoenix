# _archive — the dead Phoenix rewrite

Everything here is kept for reference and history. **Do not resurrect it to replace Halseth or the
live TypeScript bots.** See `../PHOENIX-RECKONING.md` for the full reasoning.

Phoenix was designed as a five-service Python/FastAPI rewrite that would absorb the lean BBH suite.
BBH overtook it. Halseth became the mind; the TypeScript bots grew their own inference + fallback;
Brain moved to the always-on VPS. The reliability kernel solved a problem (an offline workstation
Brain) we no longer have.

## Contents

| Path | Was | Why archived |
|------|-----|--------------|
| `services/relay/` | Redis-queue buffering layer in front of Brain | Bots call Brain `/chat` directly with their own fallback; the buffer is unused. (Archived in a prior session.) |
| `services/web_ui/` | Minimal status/chat web UI | Superseded by Hearth. (Prior session.) |
| `services/discord_bot/` | Python per-agent Discord bots | Superseded by the TypeScript bots in `nullsafe-discord`. (Prior session.) |
| `services/webmind/` | FastAPI + SQLite mind-state microservice (Heart Phase slices 2-6) | Roughly 80 migrations behind Halseth, no semantic search. Halseth is the WebMind. (Archived 2026-06-16.) |
| `integration_tests/` | End-to-end tests of the five-service topology | The topology no longer exists. Already `--ignore`d before archival. |
| `docs/PHOENIX_HEART_PHASE_PLAN.md` | The 7-slice Heart Phase master plan | Plan for the dead rewrite. |
| `docs/WEBMIND_V0_DECISION.md`, `docs/WEBMIND_V0_SCHEMA_SKETCH.md` | WebMind-as-microservice design | Superseded by Halseth's live WebMind. |

## Still live (NOT here)

- `../services/brain/` — inference orchestration + swarm. pm2 `nullsafe-brain` on the VPS.
- `../shared/` — Pydantic contracts Brain depends on.
