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

from services.webmind.contracts import (
    ContinuityNoteWriteRequest,
    MindThreadUpsertRequest,
    SessionHandoffWriteRequest,
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

    def test_mind_orient_stub(self):
        response = client.get("/mind/orient", params={"agent_id": "cypher"})
        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["endpoint"] == "mind_orient"
        assert detail["agent_id"] == "cypher"

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

