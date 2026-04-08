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
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException, Query

from services.webmind.config import Config
from services.webmind.contracts import (
    ContinuityNoteWriteRequest,
    ContinuityNoteSimpleRecord,
    ContinuityNoteSimpleWriteRequest,
    HalsethTaskSummary,
    LifeDigestResponse,
    LimbicStateRecord,
    LimbicStateWriteRequest,
    MindGroundResponse,
    MindOrientResponse,
    MindThreadRecord,
    MindThreadUpsertRequest,
    ReminderRecord,
    ReminderWriteRequest,
    SessionHandoffRecord,
    SessionHandoffWriteRequest,
)
from services.webmind.database import get_db, get_db_path, init_db

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

    async with get_db() as db:
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
    async with get_db() as db:
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

    async with get_db() as db:
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
    async with get_db() as db:
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
    """Continuity recovery snapshot: limbic_state, recent_notes, latest_handoff, top_threads."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc).isoformat()
    limbic_state = None
    recent_notes = []

    async with get_db() as db:
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

        # latest session handoff
        cursor = await db.execute(
            "SELECT * FROM session_handoffs WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        h = await cursor.fetchone()
        latest_handoff = (
            SessionHandoffRecord(
                handoff_id=h["handoff_id"],
                agent_id=h["agent_id"],
                thread_id=h["thread_id"],
                title=h["title"],
                summary=h["summary"],
                next_steps=h["next_steps"],
                open_loops=h["open_loops"],
                state_hint=h["state_hint"],
                actor=h["actor"],
                source=h["source"],
                correlation_id=h["correlation_id"],
                created_at=h["created_at"],
            )
            if h else None
        )

        # top open threads (priority desc, up to 5)
        cursor = await db.execute(
            """SELECT * FROM mind_threads WHERE agent_id = ? AND status = 'open'
               ORDER BY priority DESC, last_touched_at DESC LIMIT 5""",
            (agent_id,),
        )
        thread_rows = await cursor.fetchall()
        top_threads = [
            MindThreadRecord(
                thread_key=r["thread_key"],
                agent_id=r["agent_id"],
                title=r["title"],
                description=r["description"],
                status=r["status"],
                priority=r["priority"],
                lane=r["lane"],
                last_touched_at=r["last_touched_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                created_by_actor=r["created_by_actor"],
                updated_by_actor=r["updated_by_actor"],
                source=r["source"],
                correlation_id=r["correlation_id"],
            )
            for r in thread_rows
        ]

    return MindOrientResponse(
        agent_id=agent_id,
        limbic_state=limbic_state,
        recent_notes=recent_notes,
        latest_handoff=latest_handoff,
        top_threads=top_threads,
        generated_at=now,
    )


@app.get("/mind/ground", response_model=MindGroundResponse)
async def mind_ground(
    agent_id: str = Query(..., description="Companion agent id"),
    limit: int = Query(5, ge=1, le=50),
):
    """Actionable grounding snapshot: open threads, recent handoffs, recent notes."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM mind_threads WHERE agent_id = ? AND status = 'open'
               ORDER BY priority DESC, last_touched_at DESC LIMIT ?""",
            (agent_id, limit),
        )
        thread_rows = await cursor.fetchall()
        open_threads = [
            MindThreadRecord(
                thread_key=r["thread_key"],
                agent_id=r["agent_id"],
                title=r["title"],
                description=r["description"],
                status=r["status"],
                priority=r["priority"],
                lane=r["lane"],
                last_touched_at=r["last_touched_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                created_by_actor=r["created_by_actor"],
                updated_by_actor=r["updated_by_actor"],
                source=r["source"],
                correlation_id=r["correlation_id"],
            )
            for r in thread_rows
        ]

        cursor = await db.execute(
            "SELECT * FROM session_handoffs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        handoff_rows = await cursor.fetchall()
        recent_handoffs = [
            SessionHandoffRecord(
                handoff_id=r["handoff_id"],
                agent_id=r["agent_id"],
                thread_id=r["thread_id"],
                title=r["title"],
                summary=r["summary"],
                next_steps=r["next_steps"],
                open_loops=r["open_loops"],
                state_hint=r["state_hint"],
                actor=r["actor"],
                source=r["source"],
                correlation_id=r["correlation_id"],
                created_at=r["created_at"],
            )
            for r in handoff_rows
        ]

        cursor = await db.execute(
            "SELECT * FROM continuity_notes WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
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

    return MindGroundResponse(
        agent_id=agent_id,
        open_threads=open_threads,
        recent_handoffs=recent_handoffs,
        recent_notes=recent_notes,
        generated_at=now,
    )


@app.post("/mind/session-handoffs", status_code=201, response_model=SessionHandoffRecord)
async def create_session_handoff(request: SessionHandoffWriteRequest):
    """Write a session handoff/checkpoint."""
    handoff_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO session_handoffs
               (handoff_id, agent_id, thread_id, title, summary, next_steps, open_loops,
                state_hint, actor, source, correlation_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                handoff_id, request.agent_id, request.thread_id,
                request.title, request.summary, request.next_steps, request.open_loops,
                request.state_hint,
                request.metadata.actor, request.metadata.source, request.metadata.correlation_id,
                now,
            ),
        )
        await db.commit()

    return SessionHandoffRecord(
        handoff_id=handoff_id,
        agent_id=request.agent_id,
        thread_id=request.thread_id,
        title=request.title,
        summary=request.summary,
        next_steps=request.next_steps,
        open_loops=request.open_loops,
        state_hint=request.state_hint,
        actor=request.metadata.actor,
        source=request.metadata.source,
        correlation_id=request.metadata.correlation_id,
        created_at=now,
    )


@app.get("/mind/session-handoffs")
async def get_session_handoffs(
    agent_id: str = Query(..., description="Companion agent id"),
    limit: int = Query(5, ge=1, le=100),
):
    """List recent session handoffs for an agent, most recent first."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM session_handoffs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        rows = await cursor.fetchall()

    handoffs = [
        SessionHandoffRecord(
            handoff_id=r["handoff_id"],
            agent_id=r["agent_id"],
            thread_id=r["thread_id"],
            title=r["title"],
            summary=r["summary"],
            next_steps=r["next_steps"],
            open_loops=r["open_loops"],
            state_hint=r["state_hint"],
            actor=r["actor"],
            source=r["source"],
            correlation_id=r["correlation_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return {"handoffs": handoffs, "agent_id": agent_id}


@app.post("/mind/threads/upsert", response_model=MindThreadRecord)
async def upsert_mind_thread(request: MindThreadUpsertRequest):
    """Create or update a persistent mind thread."""
    now = datetime.now(timezone.utc).isoformat()
    thread_key = request.thread_key or str(uuid.uuid4())

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT thread_key FROM mind_threads WHERE thread_key = ? AND agent_id = ?",
            (thread_key, request.agent_id),
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute(
                """UPDATE mind_threads SET
                   title = ?, description = ?,
                   status = COALESCE(?, status),
                   priority = ?, lane = COALESCE(?, lane),
                   last_touched_at = ?, updated_at = ?,
                   updated_by_actor = ?, source = ?,
                   correlation_id = ?
                   WHERE thread_key = ? AND agent_id = ?""",
                (
                    request.title, request.description,
                    request.status,
                    request.priority,
                    request.lane,
                    now, now,
                    request.metadata.actor, request.metadata.source,
                    request.metadata.correlation_id,
                    thread_key, request.agent_id,
                ),
            )
            event_type = "updated"
        else:
            status = request.status or "open"
            await db.execute(
                """INSERT INTO mind_threads
                   (thread_key, agent_id, title, description, status, priority, lane,
                    last_touched_at, created_at, updated_at,
                    created_by_actor, updated_by_actor, source, correlation_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_key, request.agent_id, request.title, request.description,
                    status, request.priority, request.lane,
                    now, now, now,
                    request.metadata.actor, request.metadata.actor,
                    request.metadata.source, request.metadata.correlation_id,
                ),
            )
            event_type = "created"

        event_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO mind_thread_events
               (event_id, thread_key, agent_id, event_type, event_summary,
                payload_json, actor, source, correlation_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, thread_key, request.agent_id,
                event_type, request.title,
                json.dumps({"title": request.title, "priority": request.priority}),
                request.metadata.actor, request.metadata.source,
                request.metadata.correlation_id, now,
            ),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM mind_threads WHERE thread_key = ? AND agent_id = ?",
            (thread_key, request.agent_id),
        )
        row = await cursor.fetchone()

    return MindThreadRecord(
        thread_key=row["thread_key"],
        agent_id=row["agent_id"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        lane=row["lane"],
        last_touched_at=row["last_touched_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_actor=row["created_by_actor"],
        updated_by_actor=row["updated_by_actor"],
        source=row["source"],
        correlation_id=row["correlation_id"],
    )


@app.get("/mind/threads")
async def list_mind_threads(
    agent_id: str = Query(..., description="Companion agent id"),
    status: str = Query("open"),
    limit: int = Query(10, ge=1, le=100),
):
    """List persistent mind threads for an agent."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    if status not in ("open", "paused", "resolved", "archived"):
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM mind_threads WHERE agent_id = ? AND status = ?
               ORDER BY priority DESC, last_touched_at DESC LIMIT ?""",
            (agent_id, status, limit),
        )
        rows = await cursor.fetchall()

    threads = [
        MindThreadRecord(
            thread_key=r["thread_key"],
            agent_id=r["agent_id"],
            title=r["title"],
            description=r["description"],
            status=r["status"],
            priority=r["priority"],
            lane=r["lane"],
            last_touched_at=r["last_touched_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            created_by_actor=r["created_by_actor"],
            updated_by_actor=r["updated_by_actor"],
            source=r["source"],
            correlation_id=r["correlation_id"],
        )
        for r in rows
    ]
    return {"threads": threads, "agent_id": agent_id, "status": status}


# ---------------------------------------------------------------------------
# Slice 3: Life Support -- reminders + housekeeping digest
# ---------------------------------------------------------------------------

def _row_to_reminder(r) -> ReminderRecord:
    return ReminderRecord(
        reminder_id=r["reminder_id"],
        agent_id=r["agent_id"],
        title=r["title"],
        body=r["body"],
        due_at=r["due_at"],
        recurrence=r["recurrence"],
        status=r["status"],
        dismissed_at=r["dismissed_at"],
        created_by=r["created_by"],
        source=r["source"],
        created_at=r["created_at"],
    )


@app.post("/life/reminders", status_code=201, response_model=ReminderRecord)
async def create_reminder(request: ReminderWriteRequest):
    """Create a life reminder."""
    reminder_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO life_reminders
               (reminder_id, agent_id, title, body, due_at, recurrence,
                status, created_by, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (
                reminder_id, request.agent_id, request.title, request.body,
                request.due_at, request.recurrence,
                request.created_by, request.source, now,
            ),
        )
        await db.commit()

    return ReminderRecord(
        reminder_id=reminder_id,
        agent_id=request.agent_id,
        title=request.title,
        body=request.body,
        due_at=request.due_at,
        recurrence=request.recurrence,
        status="pending",
        dismissed_at=None,
        created_by=request.created_by,
        source=request.source,
        created_at=now,
    )


@app.get("/life/reminders")
async def list_reminders(
    agent_id: str = Query(..., description="Agent id or 'swarm'"),
    status: str = Query("pending"),
    limit: int = Query(20, ge=1, le=100),
):
    """List reminders for an agent, ordered by due_at ascending."""
    if agent_id not in ("drevan", "cypher", "gaia", "swarm"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    if status not in ("pending", "snoozed", "dismissed"):
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM life_reminders
               WHERE agent_id = ? AND status = ?
               ORDER BY due_at ASC LIMIT ?""",
            (agent_id, status, limit),
        )
        rows = await cursor.fetchall()

    return {"reminders": [_row_to_reminder(r) for r in rows], "agent_id": agent_id}


@app.post("/life/reminders/{reminder_id}/dismiss", response_model=ReminderRecord)
async def dismiss_reminder(reminder_id: str):
    """Mark a reminder as dismissed."""
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM life_reminders WHERE reminder_id = ?",
            (reminder_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "reminder_not_found"})
        if row["status"] == "dismissed":
            raise HTTPException(status_code=409, detail={"code": "already_dismissed"})

        await db.execute(
            "UPDATE life_reminders SET status = 'dismissed', dismissed_at = ? WHERE reminder_id = ?",
            (now, reminder_id),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM life_reminders WHERE reminder_id = ?", (reminder_id,)
        )
        updated = await cursor.fetchone()

    return _row_to_reminder(updated)


@app.get("/life/digest", response_model=LifeDigestResponse)
async def life_digest(
    agent_id: str = Query(..., description="Agent id or 'swarm'"),
    upcoming_hours: int = Query(24, ge=1, le=168, description="Hours ahead for upcoming reminders"),
):
    """Aggregated life-support view: due reminders, upcoming reminders, open threads, Halseth tasks."""
    if agent_id not in ("drevan", "cypher", "gaia", "swarm"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    horizon_iso = (now + timedelta(hours=upcoming_hours)).isoformat()

    due_reminders: list[ReminderRecord] = []
    upcoming_reminders: list[ReminderRecord] = []
    open_threads: list[MindThreadRecord] = []
    halseth_tasks: list[HalsethTaskSummary] = []
    halseth_available = False

    async with get_db() as db:
        # Due (overdue or due now)
        cursor = await db.execute(
            """SELECT * FROM life_reminders
               WHERE agent_id = ? AND status = 'pending' AND due_at <= ?
               ORDER BY due_at ASC LIMIT 20""",
            (agent_id, now_iso),
        )
        due_reminders = [_row_to_reminder(r) for r in await cursor.fetchall()]

        # Upcoming (due within the horizon window)
        cursor = await db.execute(
            """SELECT * FROM life_reminders
               WHERE agent_id = ? AND status = 'pending'
               AND due_at > ? AND due_at <= ?
               ORDER BY due_at ASC LIMIT 10""",
            (agent_id, now_iso, horizon_iso),
        )
        upcoming_reminders = [_row_to_reminder(r) for r in await cursor.fetchall()]

        # Open threads -- skip for 'swarm' (threads are per-agent)
        if agent_id != "swarm":
            cursor = await db.execute(
                """SELECT * FROM mind_threads WHERE agent_id = ? AND status = 'open'
                   ORDER BY priority DESC, last_touched_at DESC LIMIT 10""",
                (agent_id,),
            )
            open_threads = [
                MindThreadRecord(
                    thread_key=r["thread_key"], agent_id=r["agent_id"],
                    title=r["title"], description=r["description"],
                    status=r["status"], priority=r["priority"], lane=r["lane"],
                    last_touched_at=r["last_touched_at"], created_at=r["created_at"],
                    updated_at=r["updated_at"], created_by_actor=r["created_by_actor"],
                    updated_by_actor=r["updated_by_actor"], source=r["source"],
                    correlation_id=r["correlation_id"],
                )
                for r in await cursor.fetchall()
            ]

    # Halseth task aggregation (optional -- graceful degradation if not configured)
    from services.webmind.config import Config
    if Config.HALSETH_URL and Config.HALSETH_AUTH_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{Config.HALSETH_URL}/tasks",
                    headers={"Authorization": f"Bearer {Config.HALSETH_AUTH_TOKEN}"},
                    params={"status": "open", "limit": "20"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tasks = data.get("tasks") or data.get("results") or []
                    halseth_tasks = [
                        HalsethTaskSummary(
                            id=t.get("id", ""),
                            title=t.get("title", ""),
                            status=t.get("status", ""),
                            priority=t.get("priority"),
                            due_at=t.get("due_at"),
                            assigned_to=t.get("assigned_to"),
                        )
                        for t in tasks
                    ]
                    halseth_available = True
        except Exception:
            pass  # Halseth down -- digest still returns local data

    return LifeDigestResponse(
        agent_id=agent_id,
        due_reminders=due_reminders,
        upcoming_reminders=upcoming_reminders,
        open_threads=open_threads,
        halseth_tasks=halseth_tasks,
        halseth_available=halseth_available,
        generated_at=now_iso,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.WEBMIND_PORT,
        access_log=False,
    )
