#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - WebMind Service (Slice 2 scaffold)

Persistent continuity/mind-state API surface.
NEVER calls Discord directly. NEVER runs LLM inference.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query

from services.webmind.config import Config
from services.webmind.contracts import (
    ContinuityNoteWriteRequest,
    ContinuityNoteSimpleRecord,
    ContinuityNoteSimpleWriteRequest,
    LimbicStateRecord,
    LimbicStateWriteRequest,
    MindGroundResponse,
    MindOrientResponse,
    MindThreadUpsertRequest,
    SessionHandoffWriteRequest,
)
from services.webmind.database import get_db_path, init_db

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Nullsafe Phoenix WebMind",
    version="v0-slice2-scaffold",
    description="Persistent continuity and mind-state API (scaffold)",
    lifespan=lifespan,
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


# ---------------------------------------------------------------------------
# Task 3: Limbic state endpoints
# ---------------------------------------------------------------------------

@app.post("/mind/limbic", status_code=201, response_model=LimbicStateRecord)
async def write_limbic_state(request: LimbicStateWriteRequest):
    """Brain writes a new LimbicState after each synthesis pass."""
    state_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            """INSERT INTO limbic_states
               (state_id, generated_at, synthesis_source, active_concerns, live_tensions,
                drift_vector, open_questions, emotional_register, swarm_threads, companion_notes,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                state_id, now, request.synthesis_source,
                json.dumps(request.active_concerns),
                json.dumps(request.live_tensions),
                request.drift_vector,
                json.dumps(request.open_questions),
                request.emotional_register,
                json.dumps(request.swarm_threads),
                json.dumps(request.companion_notes),
                now,
            ),
        )
        await db.commit()

    return LimbicStateRecord(
        state_id=state_id,
        generated_at=now,
        synthesis_source=request.synthesis_source,
        active_concerns=request.active_concerns,
        live_tensions=request.live_tensions,
        drift_vector=request.drift_vector,
        open_questions=request.open_questions,
        emotional_register=request.emotional_register,
        swarm_threads=request.swarm_threads,
        companion_notes=request.companion_notes,
        created_at=now,
    )


@app.get("/mind/limbic/current", response_model=LimbicStateRecord)
async def get_current_limbic_state():
    """Return the most recent LimbicState. 404 if none exists."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM limbic_states ORDER BY created_at DESC, rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "no_limbic_state", "message": "No limbic state recorded yet"},
        )

    return LimbicStateRecord(
        state_id=row["state_id"],
        generated_at=row["generated_at"],
        synthesis_source=row["synthesis_source"],
        active_concerns=json.loads(row["active_concerns"]),
        live_tensions=json.loads(row["live_tensions"]),
        drift_vector=row["drift_vector"],
        open_questions=json.loads(row["open_questions"]),
        emotional_register=row["emotional_register"],
        swarm_threads=json.loads(row["swarm_threads"]),
        companion_notes=json.loads(row["companion_notes"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Task 4: Notes endpoints
# ---------------------------------------------------------------------------

@app.post("/mind/notes", status_code=201, response_model=ContinuityNoteSimpleRecord)
async def create_note(request: ContinuityNoteSimpleWriteRequest):
    """Brain writes a continuity note (from synthesis or conversation)."""
    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            """INSERT INTO continuity_notes (note_id, agent_id, thread_key, note_text, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (note_id, request.agent_id, request.thread_key, request.note_text, request.source, now),
        )
        await db.commit()

    return ContinuityNoteSimpleRecord(
        note_id=note_id,
        agent_id=request.agent_id,
        note_text=request.note_text,
        thread_key=request.thread_key,
        source=request.source,
        created_at=now,
    )


@app.get("/mind/notes")
async def list_notes(
    agent_id: str = Query(..., description="Agent or 'swarm'"),
    limit: int = Query(10, ge=1, le=100),
):
    """Return recent notes for an agent, most recent first."""
    if agent_id not in ("drevan", "cypher", "gaia", "swarm"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM continuity_notes WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        rows = await cursor.fetchall()

    notes = [
        ContinuityNoteSimpleRecord(
            note_id=r["note_id"],
            agent_id=r["agent_id"],
            note_text=r["note_text"],
            thread_key=r["thread_key"],
            source=r["source"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return {"notes": notes, "agent_id": agent_id}


# ---------------------------------------------------------------------------
# Task 5: Orient endpoint (partial)
# ---------------------------------------------------------------------------

@app.get("/mind/orient", response_model=MindOrientResponse)
async def mind_orient(
    agent_id: str = Query(..., description="Companion agent id"),
):
    """
    Continuity recovery snapshot.
    Partial implementation: returns limbic_state + recent_notes.
    identity_anchor, latest_handoff, top_threads remain unimplemented (future slices).
    """
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc).isoformat()
    limbic_state = None
    recent_notes = []

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM limbic_states ORDER BY created_at DESC, rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            limbic_state = LimbicStateRecord(
                state_id=row["state_id"],
                generated_at=row["generated_at"],
                synthesis_source=row["synthesis_source"],
                active_concerns=json.loads(row["active_concerns"]),
                live_tensions=json.loads(row["live_tensions"]),
                drift_vector=row["drift_vector"],
                open_questions=json.loads(row["open_questions"]),
                emotional_register=row["emotional_register"],
                swarm_threads=json.loads(row["swarm_threads"]),
                companion_notes=json.loads(row["companion_notes"]),
                created_at=row["created_at"],
            )

        cursor = await db.execute(
            "SELECT * FROM continuity_notes WHERE agent_id = ? ORDER BY created_at DESC LIMIT 5",
            (agent_id,),
        )
        note_rows = await cursor.fetchall()
        recent_notes = [
            ContinuityNoteSimpleRecord(
                note_id=r["note_id"],
                agent_id=r["agent_id"],
                note_text=r["note_text"],
                thread_key=r["thread_key"],
                source=r["source"],
                created_at=r["created_at"],
            )
            for r in note_rows
        ]

    return MindOrientResponse(
        agent_id=agent_id,
        limbic_state=limbic_state,
        recent_notes=recent_notes,
        generated_at=now,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.WEBMIND_PORT,
        access_log=False,
    )
