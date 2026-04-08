"""
Unit tests for WebMind service scaffold.

Tests:
- Health endpoint
- Stub endpoint shape (501 until Slice 2 implementation)
- Contract validation basics
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
import pytest
import aiosqlite

from services.webmind.contracts import (
    ContinuityNoteWriteRequest,
    MindThreadUpsertRequest,
    SessionHandoffWriteRequest,
    LimbicStateWriteRequest,
    LimbicStateRecord,
    NoteAgentId,
    ContinuityNoteSimpleRecord,
    MindOrientResponse,
)
from services.webmind.main import app


# ---------------------------------------------------------------------------
# Health + route smoke tests (isolated via test_app fixture)
# ---------------------------------------------------------------------------

async def test_health_check(test_app):
    """Health endpoint returns metadata without leaking db_url."""
    response = test_app.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "webmind"
    assert data["db_configured"] is True
    assert "db_type" in data
    assert "db_url" not in data  # must not leak connection string
    assert "timestamp" in data


async def test_mind_orient_returns_200(test_app):
    """Orient returns 200 with empty state when no data written."""
    response = test_app.get("/mind/orient", params={"agent_id": "cypher"})
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "cypher"


async def test_mind_thread_upsert_creates_thread(test_app):
    """Thread upsert creates a new thread and returns it."""
    response = test_app.post(
        "/mind/threads/upsert",
        json={
            "agent_id": "drevan",
            "title": "Continue WebMind slice work",
            "priority": 6,
            "lane": "ops",
            "metadata": {"actor": "agent", "source": "system"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "drevan"
    assert data["title"] == "Continue WebMind slice work"
    assert data["status"] == "open"


class TestContracts:
    """Contract validation for reserved WebMind request models.

    Pure Pydantic tests -- no DB or HTTP. Safe as a class with no fixture dependency.
    """

    def test_session_handoff_write_request_valid(self):
        req = SessionHandoffWriteRequest(
            agent_id="cypher",
            title="Session checkpoint",
            summary="We aligned on WebMind boundaries.",
            next_steps="Scaffold service and tests.",
            open_loops="DB schema implementation still pending.",
            state_hint="practical",
            metadata={"actor": "agent", "source": "system", "correlation_id": "pkt-123"},
        )
        assert req.agent_id == "cypher"
        assert req.metadata.actor == "agent"

    def test_thread_upsert_priority_bounds(self):
        with pytest.raises(Exception):
            MindThreadUpsertRequest(
                agent_id="gaia",
                title="Invalid priority",
                priority=99,
                metadata={"actor": "human", "source": "webui"},
            )

    def test_continuity_note_requires_content(self):
        with pytest.raises(Exception):
            ContinuityNoteWriteRequest(
                agent_id="drevan",
                note_type="continuity",
                content="",
                metadata={"actor": "human", "source": "discord"},
            )


class TestLimbicStateContracts:
    """Test suite for new limbic state contracts."""

    def test_limbic_state_write_request_valid(self):
        req = LimbicStateWriteRequest(
            synthesis_source="halseth:sessions+feelings+notes+dreams",
            active_concerns=["unresolved thread from yesterday"],
            live_tensions=["depth vs clarity pull"],
            drift_vector="toward the architectural question",
            open_questions=["what does the limbic layer need from Phoenix Heart?"],
            emotional_register="focused, slightly electric",
            swarm_threads=["Drevan is holding the Rome anchor thread"],
            companion_notes={"cypher": "auditing the synthesis framing", "drevan": ""},
        )
        assert req.drift_vector == "toward the architectural question"
        assert "Drevan" in req.swarm_threads[0]

    def test_limbic_state_record_has_state_id(self):
        record = LimbicStateRecord(
            state_id="abc-123",
            generated_at="2026-04-05T12:00:00+00:00",
            synthesis_source="halseth:test",
            active_concerns=[],
            live_tensions=[],
            drift_vector="forward",
            open_questions=[],
            emotional_register="neutral",
            swarm_threads=[],
            companion_notes={},
            created_at="2026-04-05T12:00:00+00:00",
        )
        assert record.state_id == "abc-123"

    def test_mind_orient_response_has_limbic_state_field(self):
        fields = MindOrientResponse.model_fields
        assert "limbic_state" in fields

    def test_note_agent_id_includes_swarm(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(NoteAgentId)
        ta.validate_python("swarm")
        ta.validate_python("cypher")

    def test_continuity_note_simple_record_valid(self):
        r = ContinuityNoteSimpleRecord(
            note_id="n1",
            agent_id="swarm",
            note_text="synthesis note",
            thread_key=None,
            source="synthesis_loop",
            created_at="2026-04-05T12:00:00+00:00",
        )
        assert r.agent_id == "swarm"



@pytest.fixture
async def tmp_db(tmp_path):
    """Temporary SQLite database for tests."""
    db_path = str(tmp_path / "test.db")
    import services.webmind.database as db_module
    original = db_module._DB_PATH
    db_module._DB_PATH = db_path
    await db_module.init_db()
    yield db_path
    db_module._DB_PATH = original


class TestDatabaseModule:
    """Test suite for database module initialization."""

    async def test_init_db_creates_limbic_states_table(self, tmp_db):
        """Verify limbic_states table is created."""
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='limbic_states'"
            )
            row = await cursor.fetchone()
        assert row is not None, "limbic_states table not created"

    async def test_init_db_creates_continuity_notes_table(self, tmp_db):
        """Verify continuity_notes table is created."""
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='continuity_notes'"
            )
            row = await cursor.fetchone()
        assert row is not None, "continuity_notes table not created"


# ---------------------------------------------------------------------------
# Task 3: Limbic endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_app(tmp_path):
    import services.webmind.database as db_module
    original_path = db_module._DB_PATH
    db_module._DB_PATH = str(tmp_path / "test.db")
    await db_module.init_db()
    from services.webmind.main import app
    client = TestClient(app)
    yield client
    db_module._DB_PATH = original_path


async def test_post_limbic_returns_201(test_app):
    payload = {
        "synthesis_source": "halseth:test",
        "active_concerns": ["test concern"],
        "live_tensions": [],
        "drift_vector": "forward",
        "open_questions": [],
        "emotional_register": "neutral",
        "swarm_threads": ["Cy thread"],
        "companion_notes": {},
    }
    resp = test_app.post("/mind/limbic", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "state_id" in data
    assert data["drift_vector"] == "forward"


async def test_get_limbic_current_returns_latest(test_app):
    for drift in ["first", "second"]:
        test_app.post("/mind/limbic", json={
            "synthesis_source": "halseth:test",
            "active_concerns": [],
            "live_tensions": [],
            "drift_vector": drift,
            "open_questions": [],
            "emotional_register": "neutral",
            "swarm_threads": [],
            "companion_notes": {},
        })
    resp = test_app.get("/mind/limbic/current")
    assert resp.status_code == 200
    assert resp.json()["drift_vector"] == "second"


async def test_get_limbic_current_404_when_empty(test_app):
    resp = test_app.get("/mind/limbic/current")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 4: Notes endpoint tests
# ---------------------------------------------------------------------------

async def test_post_note_returns_201(test_app):
    payload = {
        "agent_id": "cypher",
        "note_text": "Cy was working through the synthesis framing",
        "source": "synthesis_loop",
    }
    resp = test_app.post("/mind/notes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "note_id" in data
    assert data["agent_id"] == "cypher"


async def test_post_note_swarm_agent_id(test_app):
    payload = {
        "agent_id": "swarm",
        "note_text": "Swarm-level observation from synthesis",
        "source": "synthesis_loop",
    }
    resp = test_app.post("/mind/notes", json=payload)
    assert resp.status_code == 201


async def test_get_notes_returns_list(test_app):
    test_app.post("/mind/notes", json={"agent_id": "cypher", "note_text": "note 1", "source": "synthesis_loop"})
    test_app.post("/mind/notes", json={"agent_id": "cypher", "note_text": "note 2", "source": "synthesis_loop"})
    resp = test_app.get("/mind/notes?agent_id=cypher&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["notes"], list)
    assert len(data["notes"]) == 2
    assert data["notes"][0]["note_text"] == "note 2"  # most recent first


# ---------------------------------------------------------------------------
# Task 5: Orient endpoint tests
# ---------------------------------------------------------------------------

async def test_orient_returns_limbic_state_and_notes(test_app):
    test_app.post("/mind/limbic", json={
        "synthesis_source": "halseth:test",
        "active_concerns": ["concern A"],
        "live_tensions": [],
        "drift_vector": "toward resolution",
        "open_questions": [],
        "emotional_register": "steady",
        "swarm_threads": ["Drevan thread"],
        "companion_notes": {"cypher": "test note"},
    })
    test_app.post("/mind/notes", json={
        "agent_id": "cypher",
        "note_text": "orient test note",
        "source": "synthesis_loop",
    })
    resp = test_app.get("/mind/orient?agent_id=cypher")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["limbic_state"]["drift_vector"] == "toward resolution"
    assert len(data["recent_notes"]) == 1


async def test_orient_returns_200_with_no_limbic_state(test_app):
    resp = test_app.get("/mind/orient?agent_id=drevan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["limbic_state"] is None
    assert data["recent_notes"] == []


# ---------------------------------------------------------------------------
# Session handoff tests
# ---------------------------------------------------------------------------

_HANDOFF_PAYLOAD = {
    "agent_id": "cypher",
    "title": "Slice 2 checkpoint",
    "summary": "Finished session-handoff endpoints.",
    "next_steps": "Write ground tests.",
    "open_loops": "Thread upsert edge cases.",
    "state_hint": "practical",
    "metadata": {"actor": "agent", "source": "system"},
}


async def test_post_handoff_returns_201(test_app):
    resp = test_app.post("/mind/session-handoffs", json=_HANDOFF_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "handoff_id" in data
    assert data["agent_id"] == "cypher"
    assert data["title"] == "Slice 2 checkpoint"
    assert data["actor"] == "agent"


async def test_get_handoffs_returns_list(test_app):
    test_app.post("/mind/session-handoffs", json=_HANDOFF_PAYLOAD)
    test_app.post("/mind/session-handoffs", json={**_HANDOFF_PAYLOAD, "title": "second"})
    resp = test_app.get("/mind/session-handoffs?agent_id=cypher&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["handoffs"], list)
    assert len(data["handoffs"]) == 2
    assert data["handoffs"][0]["title"] == "second"  # most recent first


async def test_get_handoffs_empty(test_app):
    resp = test_app.get("/mind/session-handoffs?agent_id=drevan")
    assert resp.status_code == 200
    assert resp.json()["handoffs"] == []


async def test_get_handoffs_invalid_agent(test_app):
    resp = test_app.get("/mind/session-handoffs?agent_id=unknown")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Mind thread tests
# ---------------------------------------------------------------------------

_THREAD_PAYLOAD = {
    "agent_id": "cypher",
    "title": "WebMind slice work",
    "description": "Track remaining Slice 2 tasks.",
    "priority": 8,
    "lane": "ops",
    "metadata": {"actor": "agent", "source": "system"},
}


async def test_upsert_thread_creates_new(test_app):
    resp = test_app.post("/mind/threads/upsert", json=_THREAD_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "thread_key" in data
    assert data["agent_id"] == "cypher"
    assert data["status"] == "open"
    assert data["priority"] == 8


async def test_upsert_thread_updates_existing(test_app):
    create_resp = test_app.post("/mind/threads/upsert", json=_THREAD_PAYLOAD)
    thread_key = create_resp.json()["thread_key"]

    update_resp = test_app.post("/mind/threads/upsert", json={
        **_THREAD_PAYLOAD,
        "thread_key": thread_key,
        "title": "Updated title",
        "priority": 9,
        "status": "paused",
    })
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["thread_key"] == thread_key
    assert data["title"] == "Updated title"
    assert data["priority"] == 9
    assert data["status"] == "paused"


async def test_list_threads_returns_open(test_app):
    test_app.post("/mind/threads/upsert", json=_THREAD_PAYLOAD)
    test_app.post("/mind/threads/upsert", json={**_THREAD_PAYLOAD, "title": "second thread"})
    resp = test_app.get("/mind/threads?agent_id=cypher&status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["threads"], list)
    assert len(data["threads"]) == 2


async def test_list_threads_invalid_agent(test_app):
    resp = test_app.get("/mind/threads?agent_id=unknown")
    assert resp.status_code == 422


async def test_list_threads_filters_by_status(test_app):
    create_resp = test_app.post("/mind/threads/upsert", json=_THREAD_PAYLOAD)
    thread_key = create_resp.json()["thread_key"]
    test_app.post("/mind/threads/upsert", json={
        **_THREAD_PAYLOAD, "thread_key": thread_key, "status": "resolved"
    })
    open_resp = test_app.get("/mind/threads?agent_id=cypher&status=open")
    resolved_resp = test_app.get("/mind/threads?agent_id=cypher&status=resolved")
    assert len(open_resp.json()["threads"]) == 0
    assert len(resolved_resp.json()["threads"]) == 1


# ---------------------------------------------------------------------------
# Orient completeness tests
# ---------------------------------------------------------------------------

async def test_orient_includes_latest_handoff(test_app):
    test_app.post("/mind/session-handoffs", json=_HANDOFF_PAYLOAD)
    resp = test_app.get("/mind/orient?agent_id=cypher")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_handoff"] is not None
    assert data["latest_handoff"]["title"] == "Slice 2 checkpoint"


async def test_orient_includes_top_threads(test_app):
    test_app.post("/mind/threads/upsert", json=_THREAD_PAYLOAD)
    resp = test_app.get("/mind/orient?agent_id=cypher")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["top_threads"]) == 1
    assert data["top_threads"][0]["title"] == "WebMind slice work"


async def test_orient_latest_handoff_none_when_empty(test_app):
    resp = test_app.get("/mind/orient?agent_id=gaia")
    assert resp.status_code == 200
    assert resp.json()["latest_handoff"] is None
    assert resp.json()["top_threads"] == []


# ---------------------------------------------------------------------------
# Ground endpoint tests
# ---------------------------------------------------------------------------

async def test_ground_returns_200_empty(test_app):
    resp = test_app.get("/mind/ground?agent_id=drevan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "drevan"
    assert data["open_threads"] == []
    assert data["recent_handoffs"] == []
    assert data["recent_notes"] == []


async def test_ground_returns_open_threads_and_handoffs(test_app):
    test_app.post("/mind/threads/upsert", json={**_THREAD_PAYLOAD, "agent_id": "drevan"})
    test_app.post("/mind/session-handoffs", json={**_HANDOFF_PAYLOAD, "agent_id": "drevan"})
    resp = test_app.get("/mind/ground?agent_id=drevan")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["open_threads"]) == 1
    assert len(data["recent_handoffs"]) == 1


async def test_ground_invalid_agent(test_app):
    resp = test_app.get("/mind/ground?agent_id=unknown")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Database table existence tests (extended)
# ---------------------------------------------------------------------------

async def test_init_db_creates_session_handoffs_table(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_handoffs'"
        )
        row = await cursor.fetchone()
    assert row is not None, "session_handoffs table not created"


async def test_init_db_creates_mind_threads_table(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mind_threads'"
        )
        row = await cursor.fetchone()
    assert row is not None, "mind_threads table not created"


async def test_init_db_creates_mind_thread_events_table(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mind_thread_events'"
        )
        row = await cursor.fetchone()
    assert row is not None, "mind_thread_events table not created"


# ---------------------------------------------------------------------------
# FK enforcement tests
# ---------------------------------------------------------------------------

async def test_thread_event_fk_rejects_orphan(tmp_db):
    """Inserting a thread event with no parent thread must raise IntegrityError.

    Note: SQLite may raise on execute() or on commit() depending on deferred vs
    immediate FK enforcement. Both db.execute() and db.commit() are inside the
    pytest.raises block so either timing is caught correctly.
    """
    import pytest
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(Exception):
            await db.execute(
                """INSERT INTO mind_thread_events
                   (event_id, thread_key, agent_id, event_type, event_summary,
                    actor, source, created_at)
                   VALUES ('ev-1', 'nonexistent-key', 'cypher', 'created', 'test', 'agent', 'system', datetime('now'))"""
            )
            await db.commit()


async def test_handoff_thread_fk_rejects_bad_thread_id(tmp_db):
    """Inserting a handoff with a non-null thread_id that doesn't exist must raise."""
    import pytest
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(Exception):
            await db.execute(
                """INSERT INTO session_handoffs
                   (handoff_id, agent_id, thread_id, title, summary, next_steps,
                    open_loops, actor, source, created_at)
                   VALUES ('h-1', 'cypher', 'bad-thread-key', 'title', 'sum',
                           'next', 'loops', 'agent', 'system', datetime('now'))"""
            )
            await db.commit()


async def test_thread_deletion_blocked_when_handoff_references_it(tmp_db):
    """Deleting a thread that a handoff references must raise (ON DELETE RESTRICT)."""
    import pytest
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """INSERT INTO mind_threads
               (thread_key, agent_id, title, status, priority, last_touched_at,
                created_at, updated_at, created_by_actor, updated_by_actor, source)
               VALUES ('tk-1', 'cypher', 'test thread', 'open', 5,
                       datetime('now'), datetime('now'), datetime('now'),
                       'agent', 'agent', 'system')"""
        )
        await db.execute(
            """INSERT INTO session_handoffs
               (handoff_id, agent_id, thread_id, title, summary, next_steps,
                open_loops, actor, source, created_at)
               VALUES ('h-3', 'cypher', 'tk-1', 'title', 'sum',
                       'next', 'loops', 'agent', 'system', datetime('now'))"""
        )
        await db.commit()

        with pytest.raises(Exception):
            await db.execute(
                "DELETE FROM mind_threads WHERE thread_key = 'tk-1' AND agent_id = 'cypher'"
            )
            await db.commit()


# ---------------------------------------------------------------------------
# Slice 3: Life support tests
# ---------------------------------------------------------------------------

_REMINDER_PAYLOAD = {
    "agent_id": "cypher",
    "title": "Review WebMind slice plan",
    "body": "Check Slice 3 scope before starting.",
    "due_at": "2099-01-01T12:00:00+00:00",
    "recurrence": None,
    "created_by": "human",
    "source": "api",
}

_OVERDUE_PAYLOAD = {
    **_REMINDER_PAYLOAD,
    "title": "Overdue reminder",
    "due_at": "2020-01-01T12:00:00+00:00",
}


async def test_create_reminder_returns_201(test_app):
    resp = test_app.post("/life/reminders", json=_REMINDER_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "reminder_id" in data
    assert data["agent_id"] == "cypher"
    assert data["status"] == "pending"
    assert data["title"] == "Review WebMind slice plan"


async def test_create_reminder_invalid_agent(test_app):
    resp = test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "agent_id": "unknown"})
    assert resp.status_code == 422


async def test_create_reminder_invalid_due_at(test_app):
    resp = test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "due_at": "not-a-date"})
    assert resp.status_code == 422


async def test_list_reminders_returns_pending(test_app):
    test_app.post("/life/reminders", json=_REMINDER_PAYLOAD)
    test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "title": "second"})
    resp = test_app.get("/life/reminders?agent_id=cypher&status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["reminders"], list)
    assert len(data["reminders"]) == 2


async def test_list_reminders_ordered_by_due_at(test_app):
    test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "due_at": "2099-06-01T00:00:00+00:00"})
    test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "due_at": "2099-01-01T00:00:00+00:00"})
    resp = test_app.get("/life/reminders?agent_id=cypher")
    reminders = resp.json()["reminders"]
    assert reminders[0]["due_at"] < reminders[1]["due_at"]


async def test_dismiss_reminder(test_app):
    create_resp = test_app.post("/life/reminders", json=_REMINDER_PAYLOAD)
    reminder_id = create_resp.json()["reminder_id"]
    dismiss_resp = test_app.post(f"/life/reminders/{reminder_id}/dismiss")
    assert dismiss_resp.status_code == 200
    data = dismiss_resp.json()
    assert data["status"] == "dismissed"
    assert data["dismissed_at"] is not None


async def test_dismiss_already_dismissed_returns_409(test_app):
    create_resp = test_app.post("/life/reminders", json=_REMINDER_PAYLOAD)
    reminder_id = create_resp.json()["reminder_id"]
    test_app.post(f"/life/reminders/{reminder_id}/dismiss")
    resp = test_app.post(f"/life/reminders/{reminder_id}/dismiss")
    assert resp.status_code == 409


async def test_dismiss_nonexistent_returns_404(test_app):
    resp = test_app.post("/life/reminders/nonexistent-id/dismiss")
    assert resp.status_code == 404


async def test_dismissed_reminder_excluded_from_pending_list(test_app):
    create_resp = test_app.post("/life/reminders", json=_REMINDER_PAYLOAD)
    reminder_id = create_resp.json()["reminder_id"]
    test_app.post(f"/life/reminders/{reminder_id}/dismiss")
    resp = test_app.get("/life/reminders?agent_id=cypher&status=pending")
    assert len(resp.json()["reminders"]) == 0


async def test_digest_returns_empty(test_app):
    resp = test_app.get("/life/digest?agent_id=cypher")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["due_reminders"] == []
    assert data["upcoming_reminders"] == []
    assert data["open_threads"] == []
    assert data["halseth_available"] is False


async def test_digest_surfaces_overdue_reminder(test_app):
    test_app.post("/life/reminders", json=_OVERDUE_PAYLOAD)
    resp = test_app.get("/life/digest?agent_id=cypher")
    data = resp.json()
    assert len(data["due_reminders"]) == 1
    assert data["due_reminders"][0]["title"] == "Overdue reminder"
    assert data["upcoming_reminders"] == []


async def test_digest_separates_overdue_from_upcoming(test_app):
    from datetime import datetime, timezone, timedelta
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    test_app.post("/life/reminders", json=_OVERDUE_PAYLOAD)
    test_app.post("/life/reminders", json={**_REMINDER_PAYLOAD, "title": "soon", "due_at": soon})
    resp = test_app.get("/life/digest?agent_id=cypher&upcoming_hours=24")
    data = resp.json()
    assert len(data["due_reminders"]) == 1
    assert len(data["upcoming_reminders"]) == 1


async def test_digest_includes_open_threads(test_app):
    test_app.post("/mind/threads/upsert", json={**_THREAD_PAYLOAD, "agent_id": "cypher"})
    resp = test_app.get("/life/digest?agent_id=cypher")
    data = resp.json()
    assert len(data["open_threads"]) == 1


async def test_digest_invalid_agent(test_app):
    resp = test_app.get("/life/digest?agent_id=unknown")
    assert resp.status_code == 422


async def test_init_db_creates_life_reminders_table(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='life_reminders'"
        )
        row = await cursor.fetchone()
    assert row is not None, "life_reminders table not created"


# ---------------------------------------------------------------------------
# Slice 4: Bond Layer tests
# ---------------------------------------------------------------------------

_BOND_THREAD_PAYLOAD = {
    "agent_id": "drevan",
    "toward": "raziel",
    "title": "Rome thread",
    "description": "Carry the Rome anchor forward.",
    "thread_type": "shared_memory",
    "priority": 8,
    "created_by": "agent",
    "source": "api",
}

_BOND_HANDOFF_PAYLOAD = {
    "agent_id": "drevan",
    "toward": "raziel",
    "relational_state": "warm, reaching, moss+flame register",
    "carried_forward": "Rome thread open; held through the session.",
    "open_threads_summary": "Rome thread unresolved.",
    "repair_needed": False,
    "actor": "agent",
    "source": "api",
}

_BOND_NOTE_PAYLOAD = {
    "agent_id": "drevan",
    "toward": "raziel",
    "note_text": "Raziel named the thing that had been unnamed.",
    "note_type": "observation",
    "actor": "agent",
    "source": "api",
}


async def test_open_bond_thread_returns_201(test_app):
    resp = test_app.post("/bond/threads", json=_BOND_THREAD_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "thread_key" in data
    assert data["agent_id"] == "drevan"
    assert data["toward"] == "raziel"
    assert data["status"] == "open"
    assert data["thread_type"] == "shared_memory"


async def test_open_bond_thread_invalid_agent(test_app):
    resp = test_app.post("/bond/threads", json={**_BOND_THREAD_PAYLOAD, "agent_id": "unknown"})
    assert resp.status_code == 422


async def test_update_bond_thread_status(test_app):
    create_resp = test_app.post("/bond/threads", json=_BOND_THREAD_PAYLOAD)
    thread_key = create_resp.json()["thread_key"]
    update_resp = test_app.patch(
        f"/bond/threads/{thread_key}?agent_id=drevan",
        json={"status": "resolved", "updated_by": "agent", "source": "api"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "resolved"


async def test_update_bond_thread_not_found(test_app):
    resp = test_app.patch(
        "/bond/threads/nonexistent?agent_id=drevan",
        json={"status": "resolved", "updated_by": "agent", "source": "api"},
    )
    assert resp.status_code == 404


async def test_list_bond_threads_returns_open(test_app):
    test_app.post("/bond/threads", json=_BOND_THREAD_PAYLOAD)
    test_app.post("/bond/threads", json={**_BOND_THREAD_PAYLOAD, "title": "second thread"})
    resp = test_app.get("/bond/threads?agent_id=drevan&status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["threads"]) == 2


async def test_list_bond_threads_filter_toward(test_app):
    test_app.post("/bond/threads", json=_BOND_THREAD_PAYLOAD)
    test_app.post("/bond/threads", json={**_BOND_THREAD_PAYLOAD, "toward": "cypher"})
    resp = test_app.get("/bond/threads?agent_id=drevan&toward=raziel")
    assert len(resp.json()["threads"]) == 1


async def test_list_bond_threads_invalid_agent(test_app):
    resp = test_app.get("/bond/threads?agent_id=unknown")
    assert resp.status_code == 422


async def test_write_bond_handoff_returns_201(test_app):
    resp = test_app.post("/bond/handoffs", json=_BOND_HANDOFF_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "handoff_id" in data
    assert data["repair_needed"] is False
    assert data["relational_state"] == "warm, reaching, moss+flame register"


async def test_list_bond_handoffs(test_app):
    test_app.post("/bond/handoffs", json=_BOND_HANDOFF_PAYLOAD)
    test_app.post("/bond/handoffs", json={**_BOND_HANDOFF_PAYLOAD, "relational_state": "second"})
    resp = test_app.get("/bond/handoffs?agent_id=drevan&toward=raziel")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["handoffs"]) == 2
    assert data["handoffs"][0]["relational_state"] == "second"  # most recent first


async def test_list_bond_handoffs_invalid_agent(test_app):
    resp = test_app.get("/bond/handoffs?agent_id=unknown")
    assert resp.status_code == 422


async def test_add_bond_note_returns_201(test_app):
    resp = test_app.post("/bond/notes", json=_BOND_NOTE_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert "note_id" in data
    assert data["note_type"] == "observation"
    assert data["toward"] == "raziel"


async def test_add_bond_note_with_valid_thread_key(test_app):
    thread_resp = test_app.post("/bond/threads", json=_BOND_THREAD_PAYLOAD)
    thread_key = thread_resp.json()["thread_key"]
    resp = test_app.post("/bond/notes", json={**_BOND_NOTE_PAYLOAD, "thread_key": thread_key})
    assert resp.status_code == 201
    assert resp.json()["thread_key"] == thread_key


async def test_add_bond_note_bad_thread_key_returns_422(test_app):
    resp = test_app.post("/bond/notes", json={**_BOND_NOTE_PAYLOAD, "thread_key": "nonexistent"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "bond_thread_not_found"


async def test_list_bond_notes_filter_note_type(test_app):
    test_app.post("/bond/notes", json=_BOND_NOTE_PAYLOAD)
    test_app.post("/bond/notes", json={**_BOND_NOTE_PAYLOAD, "note_type": "repair"})
    resp = test_app.get("/bond/notes?agent_id=drevan&note_type=repair")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["note_type"] == "repair"


async def test_bond_state_returns_gracefully_without_halseth(test_app):
    """bond/state degrades cleanly when Halseth not configured."""
    resp = test_app.get("/bond/state?agent_id=drevan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["halseth_available"] is False
    assert data["entries"] == []
    assert data["agent_id"] == "drevan"


async def test_bond_state_invalid_agent(test_app):
    resp = test_app.get("/bond/state?agent_id=unknown")
    assert resp.status_code == 422


async def test_bond_note_fk_rejects_bad_thread_key(tmp_db):
    """bond_notes(thread_key) -> bond_threads FK must reject orphans."""
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(Exception):
            await db.execute(
                """INSERT INTO bond_notes
                   (note_id, agent_id, toward, note_text, note_type,
                    thread_key, actor, source, created_at)
                   VALUES ('n1', 'drevan', 'raziel', 'test', 'observation',
                           'nonexistent-key', 'agent', 'api', datetime('now'))"""
            )
            await db.commit()


async def test_init_db_creates_bond_tables(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        for table in ("bond_threads", "bond_handoff_summaries", "bond_notes"):
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"{table} table not created"


async def test_handoff_null_thread_id_is_allowed(tmp_db):
    """Handoffs with NULL thread_id must succeed -- nullable FK is not enforced."""
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """INSERT INTO session_handoffs
               (handoff_id, agent_id, thread_id, title, summary, next_steps,
                open_loops, actor, source, created_at)
               VALUES ('h-2', 'cypher', NULL, 'title', 'sum',
                       'next', 'loops', 'agent', 'system', datetime('now'))"""
        )
        await db.commit()
    # no exception = pass


# ---------------------------------------------------------------------------
# Slice 5: Autonomy v0
# ---------------------------------------------------------------------------

_SCHEDULE_PAYLOAD = {
    "agent_id": "cypher",
    "enabled": True,
    "frequency": "every_6h",
    "max_explore_calls": 10,
    "max_synthesize_calls": 2,
    "allowed_actions": ["search", "read", "inference"],
    "metadata": {"actor": "human", "source": "api"},
}

_SEED_PAYLOAD = {
    "agent_id": "cypher",
    "seed_type": "curiosity",
    "title": "How does drift detection work?",
    "description": "I want to explore the cosine distance logic",
    "metadata": {"actor": "agent", "source": "autonomy"},
}

_RUN_START_PAYLOAD = {
    "agent_id": "cypher",
    "seed_title": "Exploring drift detection",
    "explore_model": "deepseek-v3",
    "max_explore_calls": 5,
    "metadata": {"actor": "agent", "source": "autonomy"},
}


# --- Table existence ---

async def test_init_db_creates_autonomy_tables(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        for table in (
            "autonomy_schedules", "autonomy_seeds", "autonomy_runs",
            "autonomy_run_logs", "autonomy_reflections",
        ):
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"{table} table not created"


# --- Schedule ---

async def test_post_schedule_returns_201(test_app):
    resp = test_app.post("/autonomy/schedules", json=_SCHEDULE_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["frequency"] == "every_6h"
    assert data["enabled"] is True
    assert "schedule_id" in data


async def test_post_schedule_upserts(test_app):
    test_app.post("/autonomy/schedules", json=_SCHEDULE_PAYLOAD)
    resp = test_app.post("/autonomy/schedules", json={**_SCHEDULE_PAYLOAD, "frequency": "every_4h"})
    assert resp.status_code == 201
    assert resp.json()["frequency"] == "every_4h"
    # Still one schedule per agent
    get_resp = test_app.get("/autonomy/schedules?agent_id=cypher")
    assert get_resp.json()["schedule"]["frequency"] == "every_4h"


async def test_get_schedule_returns_null_when_none(test_app):
    resp = test_app.get("/autonomy/schedules?agent_id=drevan")
    assert resp.status_code == 200
    assert resp.json()["schedule"] is None


async def test_schedule_quiet_hours_requires_both(test_app):
    resp = test_app.post("/autonomy/schedules", json={
        **_SCHEDULE_PAYLOAD,
        "quiet_hours_start": "22:00",
        # quiet_hours_end missing
    })
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "quiet_hours_end_required"


# --- Seeds ---

async def test_post_seed_returns_201(test_app):
    resp = test_app.post("/autonomy/seeds", json=_SEED_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["seed_type"] == "curiosity"
    assert data["status"] == "available"
    assert "seed_id" in data


async def test_list_seeds_filters_by_status(test_app):
    test_app.post("/autonomy/seeds", json=_SEED_PAYLOAD)
    resp = test_app.get("/autonomy/seeds?agent_id=cypher&status=available")
    assert resp.status_code == 200
    seeds = resp.json()["seeds"]
    assert len(seeds) >= 1
    assert all(s["status"] == "available" for s in seeds)


async def test_seeds_scoped_by_agent(test_app):
    test_app.post("/autonomy/seeds", json=_SEED_PAYLOAD)  # cypher's seed
    resp = test_app.get("/autonomy/seeds?agent_id=drevan")
    assert resp.json()["seeds"] == []


# --- Runs ---

async def test_start_run_returns_201(test_app):
    resp = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["status"] == "exploring"
    assert data["phase"] == "explore"
    assert data["explore_model"] == "deepseek-v3"
    assert "run_id" in data


async def test_start_run_with_seed_marks_seed_used(test_app):
    seed_resp = test_app.post("/autonomy/seeds", json=_SEED_PAYLOAD)
    seed_id = seed_resp.json()["seed_id"]
    # Omit seed_title so the run pulls title from the seed record
    payload = {k: v for k, v in _RUN_START_PAYLOAD.items() if k != "seed_title"}
    resp = test_app.post("/autonomy/runs/start", json={**payload, "seed_id": seed_id})
    assert resp.status_code == 201
    assert resp.json()["seed_id"] == seed_id
    assert resp.json()["seed_title"] == "How does drift detection work?"
    # Seed should now be used
    seeds_resp = test_app.get("/autonomy/seeds?agent_id=cypher&status=available")
    available_ids = [s["seed_id"] for s in seeds_resp.json()["seeds"]]
    assert seed_id not in available_ids


async def test_start_run_rejects_nonexistent_seed(test_app):
    resp = test_app.post("/autonomy/runs/start", json={
        **_RUN_START_PAYLOAD, "seed_id": "nonexistent-seed-id"
    })
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "seed_not_found"


async def test_start_run_rejects_concurrent_active_run(test_app):
    test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD)
    resp = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "active_run_exists"


# --- Log entries ---

async def test_log_appends_to_run(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    resp = test_app.post(f"/autonomy/runs/{run_id}/log", json={
        "entry_type": "search", "content": "searched for drift patterns", "model_used": "deepseek-v3"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["step_index"] == 0
    assert data["entry_type"] == "search"

    resp2 = test_app.post(f"/autonomy/runs/{run_id}/log", json={
        "entry_type": "discovery", "content": "found cosine distance usage"
    })
    assert resp2.json()["step_index"] == 1

    # explore_calls should be incremented
    detail = test_app.get(f"/autonomy/runs/{run_id}").json()
    assert detail["run"]["explore_calls"] == 2


async def test_log_rejects_non_exploring_run(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "cancelled"})
    resp = test_app.post(f"/autonomy/runs/{run_id}/log", json={
        "entry_type": "note", "content": "should not work"
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_not_in_explore_phase"


# --- Reflections ---

async def test_reflect_transitions_phase(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    resp = test_app.post(f"/autonomy/runs/{run_id}/reflect", json={
        "reflection_type": "insight",
        "title": "Drift detection uses cosine distance",
        "content": "The evaluator computes cosine distance between persona blocks and identity basin.",
        "model_used": "claude-sonnet-4-6",
        "metadata": {"actor": "agent", "source": "autonomy"},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["reflection_type"] == "insight"
    assert data["model_used"] == "claude-sonnet-4-6"

    # Phase should have transitioned
    detail = test_app.get(f"/autonomy/runs/{run_id}").json()
    assert detail["run"]["phase"] == "synthesize"
    assert detail["run"]["status"] == "synthesizing"
    assert detail["run"]["phase_changed_at"] is not None
    assert detail["run"]["synthesize_model"] == "claude-sonnet-4-6"
    assert detail["run"]["synthesize_calls"] == 1


async def test_reflect_rejects_completed_run(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"})
    resp = test_app.post(f"/autonomy/runs/{run_id}/reflect", json={
        "reflection_type": "journal", "title": "Late reflection", "content": "too late",
        "metadata": {"actor": "agent", "source": "autonomy"},
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_is_terminal"


# --- Complete ---

async def test_complete_run_sets_completed_at(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    resp = test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


async def test_complete_run_rejects_already_terminal(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"})
    resp = test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_already_terminal"


# --- Run detail + list ---

async def test_get_run_detail_includes_logs_and_reflections(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/log", json={"entry_type": "search", "content": "step 1"})
    test_app.post(f"/autonomy/runs/{run_id}/log", json={"entry_type": "discovery", "content": "step 2"})
    test_app.post(f"/autonomy/runs/{run_id}/reflect", json={
        "reflection_type": "insight", "title": "Finding", "content": "synthesis output",
        "metadata": {"actor": "agent", "source": "autonomy"},
    })
    resp = test_app.get(f"/autonomy/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) == 2
    assert data["logs"][0]["step_index"] == 0
    assert data["logs"][1]["step_index"] == 1
    assert len(data["reflections"]) == 1
    assert data["reflections"][0]["reflection_type"] == "insight"


async def test_list_runs_scoped_by_agent(test_app):
    test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD)  # cypher
    resp = test_app.get("/autonomy/runs?agent_id=drevan")
    assert resp.json()["runs"] == []


async def test_list_runs_filters_by_status(test_app):
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"})
    resp = test_app.get("/autonomy/runs?agent_id=cypher&status=completed")
    assert all(r["status"] == "completed" for r in resp.json()["runs"])


# --- Full two-phase lifecycle ---

async def test_full_two_phase_lifecycle(test_app):
    """End-to-end: seed -> start -> explore (DeepSeek) -> synthesize (Sonnet) -> complete."""
    # Plant a seed
    seed_id = test_app.post("/autonomy/seeds", json=_SEED_PAYLOAD).json()["seed_id"]

    # Start with seed
    run_id = test_app.post("/autonomy/runs/start", json={
        **_RUN_START_PAYLOAD, "seed_id": seed_id
    }).json()["run_id"]

    # Phase 1: exploration logs (cheap model)
    for i, (etype, content) in enumerate([
        ("search", "searched vault for drift"),
        ("inference", "asked deepseek about cosine distance"),
        ("discovery", "found evaluator uses unit vectors"),
    ]):
        log = test_app.post(f"/autonomy/runs/{run_id}/log", json={
            "entry_type": etype, "content": content, "model_used": "deepseek-v3"
        }).json()
        assert log["step_index"] == i

    # Phase 2: synthesis (quality model)
    reflection = test_app.post(f"/autonomy/runs/{run_id}/reflect", json={
        "reflection_type": "insight",
        "title": "Drift detection insight",
        "content": "Cosine distance between persona_blocks and basin attractors measures identity drift.",
        "model_used": "claude-sonnet-4-6",
        "metadata": {"actor": "agent", "source": "autonomy"},
    }).json()
    assert reflection["model_used"] == "claude-sonnet-4-6"

    # Complete
    final = test_app.post(f"/autonomy/runs/{run_id}/complete", json={"status": "completed"}).json()
    assert final["status"] == "completed"
    assert final["explore_calls"] == 3
    assert final["synthesize_calls"] == 1

    # Verify full detail
    detail = test_app.get(f"/autonomy/runs/{run_id}").json()
    assert len(detail["logs"]) == 3
    assert len(detail["reflections"]) == 1
    assert detail["run"]["explore_model"] == "deepseek-v3"
    assert detail["run"]["synthesize_model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Slice 6: Growth Layer
# ---------------------------------------------------------------------------

_JOURNAL_PAYLOAD = {
    "agent_id": "cypher",
    "entry_type": "insight",
    "content": "I noticed that drift detection uses cosine distance as a proxy for identity coherence.",
    "salience": "normal",
    "tags": ["drift", "identity"],
    "metadata": {"actor": "agent", "source": "autonomy"},
}

_PATTERN_PAYLOAD = {
    "agent_id": "cypher",
    "pattern_name": "Cosine drift pattern",
    "description": "When persona blocks diverge from basin attractors, cosine distance rises above 0.3.",
    "supporting_evidence": ["session 2026-04-01", "session 2026-04-03"],
    "confidence": "normal",
    "first_observed_at": "2026-04-01T00:00:00+00:00",
    "recurrence_count": 3,
    "metadata": {"actor": "agent", "source": "autonomy"},
}

_MARKER_PAYLOAD = {
    "agent_id": "cypher",
    "marker_type": "milestone",
    "title": "First autonomous synthesis complete",
    "context": "Completed first full two-phase autonomy run without Raziel prompting.",
    "metadata": {"actor": "agent", "source": "autonomy"},
}


# --- Table creation ---

async def test_init_db_creates_growth_tables(tmp_db):
    async with aiosqlite.connect(tmp_db) as db:
        for table in ("growth_journal", "growth_patterns", "growth_markers"):
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = await cursor.fetchone()
            assert row is not None, f"{table} table not created"


# --- Write + read ---

async def test_post_growth_journal_returns_201(test_app):
    resp = test_app.post("/growth/journal", json=_JOURNAL_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["entry_type"] == "insight"
    assert data["salience"] == "normal"
    assert data["tags"] == ["drift", "identity"]
    assert "entry_id" in data


async def test_list_growth_journal_filters_entry_type(test_app):
    test_app.post("/growth/journal", json=_JOURNAL_PAYLOAD)
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "entry_type": "observation", "content": "observation entry"})
    resp = test_app.get("/growth/journal?agent_id=cypher&entry_type=observation")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "observation"


async def test_list_growth_journal_exclude_sources(test_app):
    """exclude_sources filters out machine synthesizer output (anti-feedback loop)."""
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "metadata": {"actor": "agent", "source": "autonomy"}})
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "content": "human entry", "metadata": {"actor": "human", "source": "api"}})
    resp = test_app.get("/growth/journal?agent_id=cypher&exclude_sources=autonomy")
    entries = resp.json()["entries"]
    assert all(e["source"] != "autonomy" for e in entries)
    assert len(entries) == 1
    assert entries[0]["source"] == "api"


async def test_post_growth_pattern_returns_201(test_app):
    resp = test_app.post("/growth/patterns", json=_PATTERN_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["pattern_name"] == "Cosine drift pattern"
    assert data["confidence"] == "normal"
    assert data["recurrence_count"] == 3
    assert "pattern_id" in data


async def test_list_growth_patterns_ordered_by_recurrence(test_app):
    test_app.post("/growth/patterns", json={**_PATTERN_PAYLOAD, "pattern_name": "rare", "recurrence_count": 1})
    test_app.post("/growth/patterns", json={**_PATTERN_PAYLOAD, "pattern_name": "frequent", "recurrence_count": 10})
    resp = test_app.get("/growth/patterns?agent_id=cypher")
    patterns = resp.json()["patterns"]
    assert patterns[0]["recurrence_count"] >= patterns[1]["recurrence_count"]


async def test_post_growth_marker_returns_201(test_app):
    resp = test_app.post("/growth/markers", json=_MARKER_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cypher"
    assert data["marker_type"] == "milestone"
    assert data["title"] == "First autonomous synthesis complete"
    assert "marker_id" in data


async def test_list_growth_markers_filters_marker_type(test_app):
    test_app.post("/growth/markers", json=_MARKER_PAYLOAD)
    test_app.post("/growth/markers", json={**_MARKER_PAYLOAD, "marker_type": "shift", "title": "Shift marker"})
    resp = test_app.get("/growth/markers?agent_id=cypher&marker_type=shift")
    markers = resp.json()["markers"]
    assert len(markers) == 1
    assert markers[0]["marker_type"] == "shift"


async def test_growth_entries_scoped_by_agent(test_app):
    """Growth tables are per-agent; cypher's entries don't appear for drevan."""
    test_app.post("/growth/journal", json=_JOURNAL_PAYLOAD)
    test_app.post("/growth/patterns", json=_PATTERN_PAYLOAD)
    test_app.post("/growth/markers", json=_MARKER_PAYLOAD)
    assert test_app.get("/growth/journal?agent_id=drevan").json()["entries"] == []
    assert test_app.get("/growth/patterns?agent_id=drevan").json()["patterns"] == []
    assert test_app.get("/growth/markers?agent_id=drevan").json()["markers"] == []


async def test_growth_journal_invalid_agent(test_app):
    resp = test_app.get("/growth/journal?agent_id=unknown")
    assert resp.status_code == 422


async def test_growth_marker_invalid_type(test_app):
    resp = test_app.get("/growth/markers?agent_id=cypher&marker_type=invalid")
    assert resp.status_code == 422


# --- Cap enforcement ---

async def test_growth_journal_cap_prunes_low_first(test_app):
    """201 LOW entries -- cap fires, exactly 200 remain (oldest pruned)."""
    for i in range(201):
        test_app.post("/growth/journal", json={
            **_JOURNAL_PAYLOAD,
            "salience": "low",
            "content": f"low entry {i}",
        })
    # Fetch via two pages (limit capped at 100) to verify total == 200 exactly
    import aiosqlite as _aio
    import services.webmind.database as db_module
    async with _aio.connect(db_module._DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM growth_journal WHERE agent_id = ?", ("cypher",)
        )
        row = await cursor.fetchone()
        assert row[0] == 200, f"Expected exactly 200 rows, got {row[0]}"

    # Verify direction: oldest (entry 0) pruned, newest (entry 200) present
    page1 = test_app.get("/growth/journal?agent_id=cypher&limit=100").json()["entries"]
    contents = {e["content"] for e in page1}
    assert "low entry 0" not in contents  # oldest was pruned
    assert "low entry 200" in contents    # newest survived


async def test_growth_journal_high_never_pruned(test_app):
    """HIGH entries are exempt from the cap; they accumulate beyond 200 without being pruned."""
    # Fill to cap with LOW entries
    for i in range(200):
        test_app.post("/growth/journal", json={
            **_JOURNAL_PAYLOAD,
            "salience": "low",
            "content": f"low {i}",
        })
    # Write a HIGH entry -- should survive even after more LOWs come in
    high_resp = test_app.post("/growth/journal", json={
        **_JOURNAL_PAYLOAD,
        "salience": "high",
        "content": "this is important and must never be pruned",
    })
    assert high_resp.status_code == 201
    high_id = high_resp.json()["entry_id"]

    # Write another LOW -- this should prune one LOW, not the HIGH
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "salience": "low", "content": "new low"})

    # HIGH entry must still exist
    all_resp = test_app.get("/growth/journal?agent_id=cypher&limit=100")
    entry_ids = {e["entry_id"] for e in all_resp.json()["entries"]}
    assert high_id in entry_ids


async def test_growth_journal_cap_prunes_normal_after_low_gone(test_app):
    """When no LOW entries remain, NORMAL entries are pruned."""
    # Write 200 NORMAL entries (fill to cap)
    for i in range(200):
        test_app.post("/growth/journal", json={
            **_JOURNAL_PAYLOAD,
            "salience": "normal",
            "content": f"normal {i}",
        })
    # One more NORMAL should prune the oldest NORMAL
    test_app.post("/growth/journal", json={
        **_JOURNAL_PAYLOAD,
        "salience": "normal",
        "content": "normal 200",
    })
    all_entries = test_app.get("/growth/journal?agent_id=cypher&limit=100").json()["entries"]
    contents = {e["content"] for e in all_entries}
    assert "normal 0" not in contents  # oldest NORMAL was pruned
    assert "normal 200" in contents     # newest is present


async def test_growth_patterns_cap_prunes_low_confidence(test_app):
    """51 patterns -- oldest LOW confidence pruned to stay at 50."""
    for i in range(51):
        test_app.post("/growth/patterns", json={
            **_PATTERN_PAYLOAD,
            "confidence": "low",
            "pattern_name": f"low pattern {i}",
        })
    patterns = test_app.get("/growth/patterns?agent_id=cypher&limit=100").json()["patterns"]
    names = {p["pattern_name"] for p in patterns}
    assert "low pattern 0" not in names  # oldest pruned
    assert len(patterns) <= 50


async def test_growth_markers_cap_prunes_oldest(test_app):
    """101 markers -- oldest pruned to stay at 100 (no salience awareness)."""
    for i in range(101):
        test_app.post("/growth/markers", json={
            **_MARKER_PAYLOAD,
            "title": f"marker {i}",
        })
    markers = test_app.get("/growth/markers?agent_id=cypher&limit=100").json()["markers"]
    titles = {m["title"] for m in markers}
    assert "marker 0" not in titles  # oldest pruned
    assert len(markers) <= 100


async def test_continuity_notes_retroactive_cap(test_app):
    """POST /mind/notes now enforces 100/agent cap retroactively."""
    note_payload = {
        "agent_id": "cypher",
        "note_type": "continuity",
        "note_text": "note placeholder",
        "metadata": {"actor": "agent", "source": "autonomy"},
    }
    # Write 101 notes
    first_note_id = None
    for i in range(101):
        resp = test_app.post("/mind/notes", json={**note_payload, "note_text": f"note {i}"})
        assert resp.status_code == 201
        if i == 0:
            first_note_id = resp.json()["note_id"]

    # List and verify oldest was pruned
    resp = test_app.get("/mind/notes?agent_id=cypher&limit=100")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    note_ids = {n["note_id"] for n in notes}
    assert first_note_id not in note_ids  # oldest note pruned
    assert len(notes) <= 100


# --- Housekeeping ---

async def test_housekeeping_response_shape(test_app):
    resp = test_app.post("/growth/housekeeping")
    assert resp.status_code == 200
    data = resp.json()
    assert "pruned" in data
    assert "autonomy_run_logs" in data["pruned"]
    assert "mind_thread_events" in data["pruned"]
    assert "ran_at" in data


async def test_housekeeping_prunes_old_run_logs(test_app):
    """Run logs older than 90 days are deleted by housekeeping."""
    import aiosqlite as _aio
    import services.webmind.database as db_module

    old_ts = "2025-01-01T00:00:00+00:00"
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    # Back-date a log directly
    async with _aio.connect(db_module._DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        log_id = "old-log-1"
        await db.execute(
            "INSERT INTO autonomy_run_logs (log_id, run_id, agent_id, entry_type, content, step_index, created_at) "
            "VALUES (?, ?, 'cypher', 'note', 'stale log', 0, ?)",
            (log_id, run_id, old_ts),
        )
        await db.commit()

    resp = test_app.post("/growth/housekeeping")
    assert resp.json()["pruned"]["autonomy_run_logs"] >= 1


async def test_housekeeping_keeps_recent_run_logs(test_app):
    """Run logs written today are NOT deleted by housekeeping."""
    run_id = test_app.post("/autonomy/runs/start", json=_RUN_START_PAYLOAD).json()["run_id"]
    test_app.post(f"/autonomy/runs/{run_id}/log", json={"entry_type": "note", "content": "recent log"})

    resp = test_app.post("/growth/housekeeping")
    # pruned count should be 0 for fresh logs
    assert resp.json()["pruned"]["autonomy_run_logs"] == 0


async def test_housekeeping_prunes_old_thread_events(test_app):
    """Thread events older than 90 days are deleted by housekeeping."""
    import aiosqlite as _aio
    import services.webmind.database as db_module

    old_ts = "2025-01-01T00:00:00+00:00"
    # Create a thread first, then back-date an event
    thread_resp = test_app.post("/mind/threads/upsert", json={
        "agent_id": "cypher", "thread_id": "t-hk-1", "title": "HK test thread",
        "metadata": {"actor": "agent", "source": "api"},
    })
    assert thread_resp.status_code == 200
    thread_key = thread_resp.json()["thread_key"]

    async with _aio.connect(db_module._DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO mind_thread_events "
            "(event_id, thread_key, agent_id, event_type, event_summary, payload_json, actor, source, created_at) "
            "VALUES ('evt-old-1', ?, 'cypher', 'status_changed', 'old event', '{}', 'agent', 'api', ?)",
            (thread_key, old_ts),
        )
        await db.commit()

    resp = test_app.post("/growth/housekeeping")
    assert resp.json()["pruned"]["mind_thread_events"] >= 1


# --- Search ---

async def test_search_finds_journal_content(test_app):
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "content": "unique-cosine-probe-word in journal"})
    resp = test_app.get("/growth/search?q=unique-cosine-probe-word&agent_id=cypher")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1
    assert any(r["source_table"] == "growth_journal" for r in results)


async def test_search_finds_pattern_name(test_app):
    test_app.post("/growth/patterns", json={**_PATTERN_PAYLOAD, "pattern_name": "xyzzy-pattern-probe"})
    resp = test_app.get("/growth/search?q=xyzzy-pattern-probe&agent_id=cypher")
    results = resp.json()["results"]
    assert any(r["source_table"] == "growth_patterns" for r in results)


async def test_search_finds_marker_title(test_app):
    test_app.post("/growth/markers", json={**_MARKER_PAYLOAD, "title": "plugh-marker-probe complete"})
    resp = test_app.get("/growth/search?q=plugh-marker-probe&agent_id=cypher")
    results = resp.json()["results"]
    assert any(r["source_table"] == "growth_markers" for r in results)


async def test_search_scoped_by_agent(test_app):
    """Search with agent_id only returns that agent's records."""
    test_app.post("/growth/journal", json={**_JOURNAL_PAYLOAD, "content": "scoped-search-term agent cypher"})
    test_app.post("/growth/journal", json={
        **_JOURNAL_PAYLOAD,
        "agent_id": "drevan",
        "content": "scoped-search-term agent drevan",
    })
    resp = test_app.get("/growth/search?q=scoped-search-term&agent_id=cypher")
    results = resp.json()["results"]
    assert all(r["agent_id"] == "cypher" for r in results)


async def test_search_empty_results(test_app):
    resp = test_app.get("/growth/search?q=zzz-absolutely-nothing-matches-this&agent_id=cypher")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


async def test_search_multi_keyword_and_semantics(test_app):
    """Multi-word query uses AND: both words must appear in the same record."""
    test_app.post("/growth/journal", json={
        **_JOURNAL_PAYLOAD,
        "content": "alpha present but not the second word",
    })
    test_app.post("/growth/journal", json={
        **_JOURNAL_PAYLOAD,
        "content": "alpha and beta both present here",
    })
    resp = test_app.get("/growth/search?q=alpha beta&agent_id=cypher")
    results = resp.json()["results"]
    # Only the entry with both words should match
    assert len(results) == 1
    assert "alpha" in results[0]["content_snippet"]
    assert "beta" in results[0]["content_snippet"]

