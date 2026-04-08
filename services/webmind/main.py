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
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.webmind.config import Config
from services.webmind.contracts import (
    AutonomyReflectionRecord,
    AutonomyRunCompleteRequest,
    AutonomyRunDetailResponse,
    AutonomyRunLogRecord,
    AutonomyRunLogRequest,
    AutonomyRunRecord,
    AutonomyRunReflectRequest,
    AutonomyRunStartRequest,
    AutonomyScheduleRecord,
    AutonomyScheduleWriteRequest,
    AutonomySeedRecord,
    AutonomySeedWriteRequest,
    BondHandoffRecord,
    BondHandoffWriteRequest,
    BondNoteRecord,
    BondNoteWriteRequest,
    BondStateResponse,
    BondThreadRecord,
    BondThreadUpdateRequest,
    BondThreadWriteRequest,
    ContinuityNoteWriteRequest,
    ContinuityNoteSimpleRecord,
    ContinuityNoteSimpleWriteRequest,
    HalsethRelationalStateEntry,
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


_bearer = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """Enforce Bearer token when WEBMIND_AUTH_TOKEN is configured.

    When the token is not set (local dev), all requests pass through.
    When set, any request missing or supplying the wrong token gets 401.
    """
    if not Config.WEBMIND_AUTH_TOKEN:
        return
    if credentials is None or credentials.credentials != Config.WEBMIND_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail={"code": "unauthorized"})


app = FastAPI(
    title="Nullsafe Phoenix WebMind",
    version="v0-slice4",
    description="Persistent continuity and mind-state API (scaffold)",
    lifespan=lifespan,
    dependencies=[Depends(verify_token)],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_type = "sqlite" if Config.WEBMIND_DB_URL.startswith("sqlite") else "postgres"
    return {
        "status": "ok",
        "service": "webmind",
        "version": "v0-slice2-scaffold",
        "db_configured": True,
        "db_type": db_type,
        "halseth_configured": bool(Config.HALSETH_URL),
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
        # Validate thread_id belongs to this agent before insert -- gives 422 not 500
        if request.thread_id is not None:
            cursor = await db.execute(
                "SELECT 1 FROM mind_threads WHERE thread_key = ? AND agent_id = ?",
                (request.thread_id, request.agent_id),
            )
            if await cursor.fetchone() is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "thread_not_found",
                        "message": f"thread_id '{request.thread_id}' does not exist for agent '{request.agent_id}'",
                    },
                )

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
    """Create or update a persistent mind thread.

    Uses INSERT ... ON CONFLICT DO UPDATE so the create/update decision is
    atomic -- no torn-write window between SELECT and INSERT/UPDATE.
    Previous state is read before the upsert solely for the event log payload.
    """
    now = datetime.now(timezone.utc).isoformat()
    thread_key = request.thread_key or str(uuid.uuid4())
    incoming_status = request.status or "open"

    async with get_db() as db:
        # Read previous state for event payload -- read-before-write is safe
        # because the upsert below is atomic. A concurrent delete between here
        # and the upsert would cause an FK violation on the event insert, not
        # a silent no-op.
        cursor = await db.execute(
            "SELECT status, title FROM mind_threads WHERE thread_key = ? AND agent_id = ?",
            (thread_key, request.agent_id),
        )
        previous = await cursor.fetchone()
        event_type = "updated" if previous else "created"

        # Atomic upsert -- SQLite 3.24+ ON CONFLICT DO UPDATE
        await db.execute(
            """INSERT INTO mind_threads
               (thread_key, agent_id, title, description, status, priority, lane,
                last_touched_at, created_at, updated_at,
                created_by_actor, updated_by_actor, source, correlation_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (thread_key, agent_id) DO UPDATE SET
                   title            = excluded.title,
                   description      = excluded.description,
                   status           = COALESCE(excluded.status, mind_threads.status),
                   priority         = excluded.priority,
                   lane             = COALESCE(excluded.lane, mind_threads.lane),
                   last_touched_at  = excluded.last_touched_at,
                   updated_at       = excluded.updated_at,
                   updated_by_actor = excluded.updated_by_actor,
                   source           = excluded.source,
                   correlation_id   = excluded.correlation_id""",
            (
                thread_key, request.agent_id, request.title, request.description,
                incoming_status, request.priority, request.lane,
                now, now, now,
                request.metadata.actor, request.metadata.actor,
                request.metadata.source, request.metadata.correlation_id,
            ),
        )

        # Enrich event payload with previous state so Bond Layer drift detection
        # can see what actually changed, not just the new values.
        payload: dict = {"title": request.title, "priority": request.priority}
        if event_type == "updated" and previous:
            payload["previous_status"] = previous["status"]
            payload["previous_title"] = previous["title"]
            if request.status and request.status != previous["status"]:
                event_type = "status_changed"

        event_summary = (
            request.title
            if event_type == "created"
            else f"{previous['title']} → {request.title}" if request.title != previous["title"]
            else f"status: {previous['status']} → {request.status}"
            if event_type == "status_changed"
            else f"updated: {request.title}"
        )

        event_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO mind_thread_events
               (event_id, thread_key, agent_id, event_type, event_summary,
                payload_json, actor, source, correlation_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, thread_key, request.agent_id,
                event_type, event_summary,
                json.dumps(payload),
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
        # Verify the reminder exists first (need a clean 404 vs 409 distinction).
        cursor = await db.execute(
            "SELECT status FROM life_reminders WHERE reminder_id = ?",
            (reminder_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "reminder_not_found"})

        # Conditional UPDATE: only transitions non-dismissed rows. If the row is
        # already dismissed this is a no-op (rowcount == 0) → 409.
        cursor = await db.execute(
            "UPDATE life_reminders SET status = 'dismissed', dismissed_at = ? "
            "WHERE reminder_id = ? AND status != 'dismissed'",
            (now, reminder_id),
        )
        await db.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail={"code": "already_dismissed"})

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
        except Exception as e:
            # Graceful degradation -- Halseth down or misconfigured.
            # Log at debug so operators can distinguish a typo in HALSETH_URL
            # from an expected transient outage.
            logger.debug("Halseth task fetch failed (digest will skip tasks): %s", e)

    return LifeDigestResponse(
        agent_id=agent_id,
        due_reminders=due_reminders,
        upcoming_reminders=upcoming_reminders,
        open_threads=open_threads,
        halseth_tasks=halseth_tasks,
        halseth_available=halseth_available,
        generated_at=now_iso,
    )


# ---------------------------------------------------------------------------
# Slice 4: Bond Layer
# ---------------------------------------------------------------------------

def _row_to_bond_thread(r) -> BondThreadRecord:
    return BondThreadRecord(
        thread_key=r["thread_key"], agent_id=r["agent_id"], toward=r["toward"],
        title=r["title"], description=r["description"], status=r["status"],
        thread_type=r["thread_type"], priority=r["priority"],
        created_by=r["created_by"], source=r["source"],
        created_at=r["created_at"], updated_at=r["updated_at"],
    )


def _row_to_bond_handoff(r) -> BondHandoffRecord:
    return BondHandoffRecord(
        handoff_id=r["handoff_id"], agent_id=r["agent_id"], toward=r["toward"],
        relational_state=r["relational_state"], carried_forward=r["carried_forward"],
        open_threads_summary=r["open_threads_summary"],
        repair_needed=bool(r["repair_needed"]),
        actor=r["actor"], source=r["source"], created_at=r["created_at"],
    )


def _row_to_bond_note(r) -> BondNoteRecord:
    return BondNoteRecord(
        note_id=r["note_id"], agent_id=r["agent_id"], toward=r["toward"],
        note_text=r["note_text"], note_type=r["note_type"],
        thread_key=r["thread_key"], actor=r["actor"], source=r["source"],
        created_at=r["created_at"],
    )


@app.get("/bond/state", response_model=BondStateResponse)
async def bond_state_read(
    agent_id: str = Query(..., description="Companion agent id"),
    toward: str = Query(None, description="Filter by person (e.g. 'raziel')"),
    limit: int = Query(10, ge=1, le=50),
):
    """Proxy companion relational state from Halseth.

    Halseth is authoritative -- Phoenix does not store relational state.
    Returns gracefully with halseth_available=False when unconfigured.

    IMPORTANT: Halseth relational_deltas has two row shapes (legacy HTTP rows
    vs MCP rows). This endpoint reads companion_relational_state only, which
    is a clean single-shape table. Do NOT query relational_deltas without
    the dual-condition filter: WHERE (companion_id = ? OR (agent = ? AND delta_text IS NOT NULL))
    """
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc).isoformat()
    entries: list[HalsethRelationalStateEntry] = []
    halseth_available = False

    if Config.HALSETH_URL and Config.HALSETH_AUTH_TOKEN:
        try:
            params: dict = {"companion_id": agent_id, "limit": str(limit)}
            if toward:
                params["toward"] = toward
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{Config.HALSETH_URL}/companion-relational-state",
                    headers={"Authorization": f"Bearer {Config.HALSETH_AUTH_TOKEN}"},
                    params=params,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    rows = data.get("states") or data.get("results") or []
                    entries = [
                        HalsethRelationalStateEntry(
                            id=r.get("id", ""),
                            companion_id=r.get("companion_id", ""),
                            toward=r.get("toward", ""),
                            state_text=r.get("state_text", ""),
                            weight=r.get("weight", 0.5),
                            state_type=r.get("state_type", "feeling"),
                            noted_at=r.get("noted_at", ""),
                        )
                        for r in rows
                    ]
                    halseth_available = True
        except Exception as e:
            logger.debug("Halseth relational state fetch failed: %s", e)

    return BondStateResponse(
        agent_id=agent_id,
        toward=toward,
        entries=entries,
        halseth_available=halseth_available,
        generated_at=now,
    )


@app.post("/bond/threads", status_code=201, response_model=BondThreadRecord)
async def open_bond_thread(request: BondThreadWriteRequest):
    """Open a new relational bond thread."""
    thread_key = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO bond_threads
               (thread_key, agent_id, toward, title, description, status,
                thread_type, priority, created_by, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)""",
            (
                thread_key, request.agent_id, request.toward, request.title,
                request.description, request.thread_type, request.priority,
                request.created_by, request.source, now, now,
            ),
        )
        await db.commit()

    return BondThreadRecord(
        thread_key=thread_key, agent_id=request.agent_id, toward=request.toward,
        title=request.title, description=request.description, status="open",
        thread_type=request.thread_type, priority=request.priority,
        created_by=request.created_by, source=request.source,
        created_at=now, updated_at=now,
    )


@app.patch("/bond/threads/{thread_key}", response_model=BondThreadRecord)
async def update_bond_thread(
    thread_key: str,
    request: BondThreadUpdateRequest,
    agent_id: str = Query(..., description="Owning companion agent id"),
):
    """Update an existing bond thread (status, title, priority, description).

    agent_id is required to scope the lookup -- thread_keys are unique per agent.
    """
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM bond_threads WHERE thread_key = ? AND agent_id = ?",
            (thread_key, agent_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "bond_thread_not_found"})

        await db.execute(
            """UPDATE bond_threads SET
               title       = COALESCE(?, title),
               description = COALESCE(?, description),
               status      = COALESCE(?, status),
               priority    = COALESCE(?, priority),
               source      = ?,
               updated_at  = ?
               WHERE thread_key = ? AND agent_id = ?""",
            (
                request.title, request.description, request.status, request.priority,
                request.source, now, thread_key, agent_id,
            ),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM bond_threads WHERE thread_key = ? AND agent_id = ?",
            (thread_key, agent_id),
        )
        updated = await cursor.fetchone()

    return _row_to_bond_thread(updated)


@app.get("/bond/threads")
async def list_bond_threads(
    agent_id: str = Query(..., description="Companion agent id"),
    toward: str = Query(None, description="Filter by person"),
    status: str = Query("open"),
    limit: int = Query(20, ge=1, le=100),
):
    """List bond threads for an agent, optionally filtered by toward + status."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    if status not in ("open", "paused", "resolved", "archived"):
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})

    async with get_db() as db:
        if toward:
            cursor = await db.execute(
                """SELECT * FROM bond_threads WHERE agent_id = ? AND toward = ? AND status = ?
                   ORDER BY priority DESC, updated_at DESC LIMIT ?""",
                (agent_id, toward, status, limit),
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM bond_threads WHERE agent_id = ? AND status = ?
                   ORDER BY priority DESC, updated_at DESC LIMIT ?""",
                (agent_id, status, limit),
            )
        rows = await cursor.fetchall()

    return {"threads": [_row_to_bond_thread(r) for r in rows], "agent_id": agent_id}


@app.post("/bond/handoffs", status_code=201, response_model=BondHandoffRecord)
async def write_bond_handoff(request: BondHandoffWriteRequest):
    """Write a relational-specific session handoff summary."""
    handoff_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO bond_handoff_summaries
               (handoff_id, agent_id, toward, relational_state, carried_forward,
                open_threads_summary, repair_needed, actor, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                handoff_id, request.agent_id, request.toward,
                request.relational_state, request.carried_forward,
                request.open_threads_summary, int(request.repair_needed),
                request.actor, request.source, now,
            ),
        )
        await db.commit()

    return BondHandoffRecord(
        handoff_id=handoff_id, agent_id=request.agent_id, toward=request.toward,
        relational_state=request.relational_state, carried_forward=request.carried_forward,
        open_threads_summary=request.open_threads_summary,
        repair_needed=request.repair_needed,
        actor=request.actor, source=request.source, created_at=now,
    )


@app.get("/bond/handoffs")
async def list_bond_handoffs(
    agent_id: str = Query(..., description="Companion agent id"),
    toward: str = Query(None, description="Filter by person"),
    limit: int = Query(5, ge=1, le=50),
):
    """List recent bond handoff summaries, most recent first."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    async with get_db() as db:
        if toward:
            cursor = await db.execute(
                """SELECT * FROM bond_handoff_summaries
                   WHERE agent_id = ? AND toward = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (agent_id, toward, limit),
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM bond_handoff_summaries
                   WHERE agent_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (agent_id, limit),
            )
        rows = await cursor.fetchall()

    return {"handoffs": [_row_to_bond_handoff(r) for r in rows], "agent_id": agent_id}


@app.post("/bond/notes", status_code=201, response_model=BondNoteRecord)
async def add_bond_note(request: BondNoteWriteRequest):
    """Append a note about the bond with a specific person."""
    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        # Validate thread_key if provided -- gives 422 not 500
        if request.thread_key is not None:
            cursor = await db.execute(
                "SELECT 1 FROM bond_threads WHERE thread_key = ?", (request.thread_key,)
            )
            if await cursor.fetchone() is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "bond_thread_not_found",
                        "message": f"thread_key '{request.thread_key}' does not exist",
                    },
                )

        await db.execute(
            """INSERT INTO bond_notes
               (note_id, agent_id, toward, note_text, note_type,
                thread_key, actor, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                note_id, request.agent_id, request.toward, request.note_text,
                request.note_type, request.thread_key,
                request.actor, request.source, now,
            ),
        )
        await db.commit()

    return BondNoteRecord(
        note_id=note_id, agent_id=request.agent_id, toward=request.toward,
        note_text=request.note_text, note_type=request.note_type,
        thread_key=request.thread_key, actor=request.actor,
        source=request.source, created_at=now,
    )


@app.get("/bond/notes")
async def list_bond_notes(
    agent_id: str = Query(..., description="Companion agent id"),
    toward: str = Query(None, description="Filter by person"),
    note_type: str = Query(None, description="Filter by note_type"),
    limit: int = Query(20, ge=1, le=100),
):
    """List bond notes for an agent, most recent first."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    if note_type and note_type not in ("observation", "repair", "commitment", "gratitude", "rupture"):
        raise HTTPException(status_code=422, detail={"code": "invalid_note_type"})

    async with get_db() as db:
        conditions = ["agent_id = ?"]
        params: list = [agent_id]
        if toward:
            conditions.append("toward = ?")
            params.append(toward)
        if note_type:
            conditions.append("note_type = ?")
            params.append(note_type)
        params.append(limit)

        cursor = await db.execute(
            f"SELECT * FROM bond_notes WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()

    return {"notes": [_row_to_bond_note(r) for r in rows], "agent_id": agent_id}


# ---------------------------------------------------------------------------
# Slice 5: Autonomy v0
# ---------------------------------------------------------------------------

def _row_to_schedule(row) -> AutonomyScheduleRecord:
    return AutonomyScheduleRecord(
        schedule_id=row["schedule_id"],
        agent_id=row["agent_id"],
        enabled=bool(row["enabled"]),
        frequency=row["frequency"],
        max_explore_calls=row["max_explore_calls"],
        max_synthesize_calls=row["max_synthesize_calls"],
        quiet_hours_start=row["quiet_hours_start"],
        quiet_hours_end=row["quiet_hours_end"],
        allowed_actions=json.loads(row["allowed_actions"]),
        actor=row["actor"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_seed(row) -> AutonomySeedRecord:
    return AutonomySeedRecord(
        seed_id=row["seed_id"],
        agent_id=row["agent_id"],
        seed_type=row["seed_type"],
        title=row["title"],
        description=row["description"],
        source_ref=row["source_ref"],
        status=row["status"],
        planted_by=row["planted_by"],
        source=row["source"],
        created_at=row["created_at"],
    )


def _row_to_run(row) -> AutonomyRunRecord:
    return AutonomyRunRecord(
        run_id=row["run_id"],
        agent_id=row["agent_id"],
        seed_id=row["seed_id"],
        phase=row["phase"],
        status=row["status"],
        explore_model=row["explore_model"],
        synthesize_model=row["synthesize_model"],
        explore_calls=row["explore_calls"],
        synthesize_calls=row["synthesize_calls"],
        max_explore_calls=row["max_explore_calls"],
        seed_title=row["seed_title"],
        error_message=row["error_message"],
        actor=row["actor"],
        source=row["source"],
        correlation_id=row["correlation_id"],
        started_at=row["started_at"],
        phase_changed_at=row["phase_changed_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _row_to_run_log(row) -> AutonomyRunLogRecord:
    return AutonomyRunLogRecord(
        log_id=row["log_id"],
        run_id=row["run_id"],
        agent_id=row["agent_id"],
        entry_type=row["entry_type"],
        content=row["content"],
        model_used=row["model_used"],
        token_count=row["token_count"],
        step_index=row["step_index"],
        created_at=row["created_at"],
    )


def _row_to_reflection(row) -> AutonomyReflectionRecord:
    return AutonomyReflectionRecord(
        reflection_id=row["reflection_id"],
        run_id=row["run_id"],
        agent_id=row["agent_id"],
        reflection_type=row["reflection_type"],
        title=row["title"],
        content=row["content"],
        model_used=row["model_used"],
        target_ref=row["target_ref"],
        actor=row["actor"],
        source=row["source"],
        created_at=row["created_at"],
    )


@app.post("/autonomy/schedules", response_model=AutonomyScheduleRecord, status_code=201)
async def upsert_autonomy_schedule(request: AutonomyScheduleWriteRequest):
    """Create or update an autonomy schedule for a companion (one per companion)."""
    if request.quiet_hours_start and not request.quiet_hours_end:
        raise HTTPException(status_code=422, detail={"code": "quiet_hours_end_required"})
    if request.quiet_hours_end and not request.quiet_hours_start:
        raise HTTPException(status_code=422, detail={"code": "quiet_hours_start_required"})

    now = datetime.now(timezone.utc).isoformat()
    schedule_id = str(uuid.uuid4())

    async with get_db() as db:
        await db.execute(
            """INSERT INTO autonomy_schedules
               (schedule_id, agent_id, enabled, frequency, max_explore_calls,
                max_synthesize_calls, quiet_hours_start, quiet_hours_end,
                allowed_actions, actor, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_id) DO UPDATE SET
                   enabled              = excluded.enabled,
                   frequency            = excluded.frequency,
                   max_explore_calls    = excluded.max_explore_calls,
                   max_synthesize_calls = excluded.max_synthesize_calls,
                   quiet_hours_start    = excluded.quiet_hours_start,
                   quiet_hours_end      = excluded.quiet_hours_end,
                   allowed_actions      = excluded.allowed_actions,
                   actor                = excluded.actor,
                   source               = excluded.source,
                   updated_at           = excluded.updated_at""",
            (
                schedule_id, request.agent_id, int(request.enabled),
                request.frequency, request.max_explore_calls, request.max_synthesize_calls,
                request.quiet_hours_start, request.quiet_hours_end,
                json.dumps(request.allowed_actions),
                request.metadata.actor, request.metadata.source,
                now, now,
            ),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM autonomy_schedules WHERE agent_id = ?", (request.agent_id,)
        )
        row = await cursor.fetchone()

    return _row_to_schedule(row)


@app.get("/autonomy/schedules")
async def get_autonomy_schedule(agent_id: str = Query(...)):
    """Get the autonomy schedule for a companion."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM autonomy_schedules WHERE agent_id = ?", (agent_id,)
        )
        row = await cursor.fetchone()

    return {"schedule": _row_to_schedule(row) if row else None, "agent_id": agent_id}


@app.post("/autonomy/seeds", response_model=AutonomySeedRecord, status_code=201)
async def plant_seed(request: AutonomySeedWriteRequest):
    """Plant an autonomy seed (companion interest, curiosity, dream, or Raziel-given topic)."""
    now = datetime.now(timezone.utc).isoformat()
    seed_id = str(uuid.uuid4())

    async with get_db() as db:
        await db.execute(
            """INSERT INTO autonomy_seeds
               (seed_id, agent_id, seed_type, title, description, source_ref,
                status, planted_by, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'available', ?, ?, ?)""",
            (
                seed_id, request.agent_id, request.seed_type,
                request.title, request.description, request.source_ref,
                request.metadata.actor, request.metadata.source, now,
            ),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM autonomy_seeds WHERE seed_id = ?", (seed_id,)
        )
        row = await cursor.fetchone()

    return _row_to_seed(row)


@app.get("/autonomy/seeds")
async def list_seeds(
    agent_id: str = Query(...),
    status: str = Query("available"),
    limit: int = Query(10, ge=1, le=50),
):
    """List autonomy seeds for a companion, filtered by status."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    if status not in ("available", "used", "expired", "dismissed"):
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM autonomy_seeds WHERE agent_id = ? AND status = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (agent_id, status, limit),
        )
        rows = await cursor.fetchall()

    return {"seeds": [_row_to_seed(r) for r in rows], "agent_id": agent_id}


@app.post("/autonomy/runs/start", response_model=AutonomyRunRecord, status_code=201)
async def start_autonomy_run(request: AutonomyRunStartRequest):
    """Begin an autonomous run. Marks seed as used; 409 if an active run already exists."""
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        # Guard: one active run per companion
        cursor = await db.execute(
            "SELECT run_id FROM autonomy_runs WHERE agent_id = ? AND status IN ('exploring', 'synthesizing')",
            (request.agent_id,),
        )
        active = await cursor.fetchone()
        if active:
            raise HTTPException(status_code=409, detail={"code": "active_run_exists", "run_id": active["run_id"]})

        seed_title = request.seed_title
        if request.seed_id:
            cursor = await db.execute(
                "SELECT seed_id, title FROM autonomy_seeds WHERE seed_id = ? AND agent_id = ?",
                (request.seed_id, request.agent_id),
            )
            seed_row = await cursor.fetchone()
            if not seed_row:
                raise HTTPException(status_code=422, detail={"code": "seed_not_found"})
            if not seed_title:
                seed_title = seed_row["title"]
            await db.execute(
                "UPDATE autonomy_seeds SET status = 'used' WHERE seed_id = ?",
                (request.seed_id,),
            )

        run_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO autonomy_runs
               (run_id, agent_id, seed_id, phase, status, explore_model,
                max_explore_calls, seed_title, actor, source, correlation_id, started_at, created_at)
               VALUES (?, ?, ?, 'explore', 'exploring', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, request.agent_id, request.seed_id,
                request.explore_model, request.max_explore_calls, seed_title,
                request.metadata.actor, request.metadata.source,
                request.metadata.correlation_id, now, now,
            ),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM autonomy_runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()

    return _row_to_run(row)


@app.post("/autonomy/runs/{run_id}/log", response_model=AutonomyRunLogRecord, status_code=201)
async def append_run_log(run_id: str, request: AutonomyRunLogRequest):
    """Append an exploration log entry (Phase 1). Increments explore_calls on the run."""
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT agent_id, status FROM autonomy_runs WHERE run_id = ?", (run_id,)
        )
        run = await cursor.fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail={"code": "run_not_found"})
        if run["status"] != "exploring":
            raise HTTPException(status_code=409, detail={"code": "run_not_in_explore_phase", "status": run["status"]})

        cursor = await db.execute(
            "SELECT COALESCE(MAX(step_index), -1) AS max_step FROM autonomy_run_logs WHERE run_id = ?",
            (run_id,),
        )
        step_row = await cursor.fetchone()
        step_index = step_row["max_step"] + 1

        log_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO autonomy_run_logs
               (log_id, run_id, agent_id, entry_type, content, model_used, token_count, step_index, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, run_id, run["agent_id"], request.entry_type, request.content,
             request.model_used, request.token_count, step_index, now),
        )
        await db.execute(
            "UPDATE autonomy_runs SET explore_calls = explore_calls + 1 WHERE run_id = ?",
            (run_id,),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM autonomy_run_logs WHERE log_id = ?", (log_id,))
        row = await cursor.fetchone()

    return _row_to_run_log(row)


@app.post("/autonomy/runs/{run_id}/reflect", response_model=AutonomyReflectionRecord, status_code=201)
async def write_run_reflection(run_id: str, request: AutonomyRunReflectRequest):
    """Write a Phase 2 synthesis reflection. Auto-transitions run from explore to synthesize phase."""
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT agent_id, status, phase, source, actor FROM autonomy_runs WHERE run_id = ?",
            (run_id,),
        )
        run = await cursor.fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail={"code": "run_not_found"})
        if run["status"] in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=409, detail={"code": "run_is_terminal", "status": run["status"]})

        # Auto-transition: first reflection moves run from explore phase to synthesize
        if run["phase"] == "explore":
            await db.execute(
                "UPDATE autonomy_runs SET phase = 'synthesize', status = 'synthesizing', phase_changed_at = ? WHERE run_id = ?",
                (now, run_id),
            )

        if request.model_used:
            await db.execute(
                "UPDATE autonomy_runs SET synthesize_model = COALESCE(synthesize_model, ?) WHERE run_id = ?",
                (request.model_used, run_id),
            )

        await db.execute(
            "UPDATE autonomy_runs SET synthesize_calls = synthesize_calls + 1 WHERE run_id = ?",
            (run_id,),
        )

        reflection_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO autonomy_reflections
               (reflection_id, run_id, agent_id, reflection_type, title, content,
                model_used, target_ref, actor, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reflection_id, run_id, run["agent_id"],
                request.reflection_type, request.title, request.content,
                request.model_used, request.target_ref,
                run["actor"], run["source"], now,
            ),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM autonomy_reflections WHERE reflection_id = ?", (reflection_id,)
        )
        row = await cursor.fetchone()

    return _row_to_reflection(row)


@app.post("/autonomy/runs/{run_id}/complete", response_model=AutonomyRunRecord)
async def complete_autonomy_run(run_id: str, request: AutonomyRunCompleteRequest):
    """Mark a run as completed, failed, or cancelled."""
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM autonomy_runs WHERE run_id = ?", (run_id,)
        )
        run = await cursor.fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail={"code": "run_not_found"})
        if run["status"] in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=409, detail={"code": "run_already_terminal", "status": run["status"]})

        await db.execute(
            "UPDATE autonomy_runs SET status = ?, completed_at = ?, error_message = ? WHERE run_id = ?",
            (request.status, now, request.error_message, run_id),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM autonomy_runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()

    return _row_to_run(row)


@app.get("/autonomy/runs/{run_id}", response_model=AutonomyRunDetailResponse)
async def get_run_detail(run_id: str):
    """Get full run detail: run record, exploration logs, and synthesis reflections."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM autonomy_runs WHERE run_id = ?", (run_id,))
        run_row = await cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail={"code": "run_not_found"})

        cursor = await db.execute(
            "SELECT * FROM autonomy_run_logs WHERE run_id = ? ORDER BY step_index",
            (run_id,),
        )
        log_rows = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT * FROM autonomy_reflections WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        )
        reflection_rows = await cursor.fetchall()

    return AutonomyRunDetailResponse(
        run=_row_to_run(run_row),
        logs=[_row_to_run_log(r) for r in log_rows],
        reflections=[_row_to_reflection(r) for r in reflection_rows],
    )


@app.get("/autonomy/runs")
async def list_autonomy_runs(
    agent_id: str = Query(...),
    status: str = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    """List recent autonomous runs for a companion."""
    if agent_id not in ("drevan", "cypher", "gaia"):
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_id"})
    valid_statuses = ("exploring", "synthesizing", "completed", "failed", "cancelled")
    if status and status not in valid_statuses:
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})

    async with get_db() as db:
        if status:
            cursor = await db.execute(
                "SELECT * FROM autonomy_runs WHERE agent_id = ? AND status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (agent_id, status, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM autonomy_runs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit),
            )
        rows = await cursor.fetchall()

    return {"runs": [_row_to_run(r) for r in rows], "agent_id": agent_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.WEBMIND_PORT,
        access_log=False,
    )
