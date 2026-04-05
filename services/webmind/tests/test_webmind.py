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

client = TestClient(app)


class TestHealthEndpoint:
    """Test suite for /health endpoint."""

    def test_health_check(self):
        """Health endpoint returns service metadata."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "webmind"
        assert data["version"] == "v0-slice2-scaffold"
        assert "db_url" in data
        assert "timestamp" in data


class TestStubEndpoints:
    """Validate route presence before repository implementation lands."""

    async def test_mind_orient_returns_200(self, test_app):
        # orient is now implemented; returns 200 with empty state (no db writes here)
        response = test_app.get("/mind/orient", params={"agent_id": "cypher"})
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "cypher"

    def test_mind_thread_upsert_stub_validates_contract(self):
        response = client.post(
            "/mind/threads/upsert",
            json={
                "agent_id": "drevan",
                "title": "Continue WebMind slice work",
                "priority": 6,
                "lane": "ops",
                "metadata": {"actor": "agent", "source": "system"},
            },
        )
        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["endpoint"] == "mind_thread_upsert"
        assert detail["agent_id"] == "drevan"


class TestContracts:
    """Contract validation for reserved WebMind request models."""

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
    db_module._DB_PATH = str(tmp_path / "test.db")
    await db_module.init_db()
    from services.webmind.main import app
    return TestClient(app)


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

