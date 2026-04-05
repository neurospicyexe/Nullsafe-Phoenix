#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - WebMind Service (Slice 2 scaffold)

Persistent continuity/mind-state API surface.
NEVER calls Discord directly. NEVER runs LLM inference.
"""

import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query

from services.webmind.config import Config
from services.webmind.contracts import (
    ContinuityNoteWriteRequest,
    MindGroundResponse,
    MindOrientResponse,
    SessionHandoffWriteRequest,
    MindThreadUpsertRequest,
)

# Load environment variables (service-local first)
load_dotenv(".env.webmind")

logging.basicConfig(
    level=getattr(logging, Config.WEBMIND_LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

try:
    Config.validate()
    Config.ensure_dev_paths()
    Config.print_safe_summary()
except Exception as e:
    logger.error(f"WebMind configuration validation failed: {e}")
    raise

app = FastAPI(
    title="Nullsafe Phoenix WebMind",
    version="v0-slice2-scaffold",
    description="Persistent continuity and mind-state API (scaffold)",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "webmind",
        "version": "v0-slice2-scaffold",
        "db_url": Config.WEBMIND_DB_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/mind/orient", response_model=MindOrientResponse)
async def mind_orient(
    agent_id: str = Query(..., description="Companion agent id"),
):
    """Continuity recovery snapshot (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_orient",
            "agent_id": agent_id,
            "message": "WebMind v0 read model not implemented yet (Slice 2 scaffold)",
        },
    )


@app.get("/mind/ground", response_model=MindGroundResponse)
async def mind_ground(
    agent_id: str = Query(..., description="Companion agent id"),
    limit: int = Query(5, ge=1, le=50),
):
    """Actionable grounding snapshot (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_ground",
            "agent_id": agent_id,
            "limit": limit,
            "message": "WebMind v0 grounding view not implemented yet (Slice 2 scaffold)",
        },
    )


@app.get("/mind/session-handoffs")
async def get_session_handoffs(
    agent_id: str = Query(..., description="Companion agent id"),
    limit: int = Query(5, ge=1, le=100),
):
    """List recent handoffs (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_session_handoff_read",
            "agent_id": agent_id,
            "limit": limit,
        },
    )


@app.post("/mind/session-handoffs")
async def create_session_handoff(request: SessionHandoffWriteRequest):
    """Write a session handoff/checkpoint (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_session_handoff_write",
            "agent_id": request.agent_id,
        },
    )


@app.get("/mind/threads")
async def list_mind_threads(
    agent_id: str = Query(..., description="Companion agent id"),
    status: str = Query("open"),
    limit: int = Query(10, ge=1, le=100),
):
    """List persistent mind threads (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_thread_list",
            "agent_id": agent_id,
            "status": status,
            "limit": limit,
        },
    )


@app.post("/mind/threads/upsert")
async def upsert_mind_thread(request: MindThreadUpsertRequest):
    """Create/update a persistent mind thread (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_thread_upsert",
            "agent_id": request.agent_id,
            "thread_key": request.thread_key,
        },
    )


@app.post("/mind/notes")
async def create_continuity_note(request: ContinuityNoteWriteRequest):
    """Append a continuity note (stub)."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "endpoint": "mind_note_add",
            "agent_id": request.agent_id,
            "thread_key": request.thread_key,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.WEBMIND_PORT,
        access_log=False,
    )

