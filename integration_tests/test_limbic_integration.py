"""
Integration tests for the Limbic System pipeline.

Tests the actual seam: WebMind → OrientCache → AgentRouter system_prompt injection.
No mocks in the data path -- only InferenceClient is mocked to avoid real LLM calls.

Uses httpx ASGITransport to run WebMind in-process without a server.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx
from httpx import ASGITransport, AsyncClient

from services.brain.agents.router import AgentRouter
from services.brain.identity.loader import IdentityLoader
from services.brain.synthesis.orient_cache import OrientCache
from services.brain.webmind_client import WebMindClient
from shared.contracts import ThoughtPacket


class _ASGIWebMindClient(WebMindClient):
    """WebMindClient variant that routes all HTTP calls through an ASGI app in-process."""

    def __init__(self, app):
        super().__init__(url="http://test")
        self._asgi_app = app

    async def get_orient(self, agent_id: str):
        async with AsyncClient(
            transport=ASGITransport(app=self._asgi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/mind/orient", params={"agent_id": agent_id})
            if resp.status_code != 200:
                return None
            return resp.json()


@pytest.fixture
async def webmind_app(tmp_path):
    """WebMind FastAPI app with an isolated SQLite DB."""
    import services.webmind.database as db_module

    db_module._DB_PATH = str(tmp_path / "webmind_integration.db")
    await db_module.init_db()

    from services.webmind.main import app

    return app


async def test_orient_inject_roundtrip(webmind_app):
    """
    Full limbic roundtrip:
    1. Write a LimbicState to WebMind
    2. AgentRouter + OrientCache reads it via GET /mind/orient
    3. Assert [SWARM STATE] block appears in the system_prompt passed to inference
    """
    # 1. Write a limbic state directly to WebMind
    async with AsyncClient(
        transport=ASGITransport(app=webmind_app), base_url="http://test"
    ) as wm_http:
        resp = await wm_http.post(
            "/mind/limbic",
            json={
                "synthesis_source": "halseth:integration-test",
                "active_concerns": ["integration test concern"],
                "live_tensions": [],
                "drift_vector": "toward integration clarity",
                "open_questions": [],
                "emotional_register": "focused and electric",
                "swarm_threads": ["Cy thread from integration test"],
                "companion_notes": {"cypher": "checking the seam holds"},
            },
        )
        assert resp.status_code == 201, f"WebMind write failed: {resp.text}"

    # 2. Wire up the stack with real WebMind (in-process) + real OrientCache
    webmind_client = _ASGIWebMindClient(webmind_app)
    orient_cache = OrientCache(webmind_client=webmind_client, ttl_seconds=300)

    # 3. Mock InferenceClient -- captures system_prompt without making LLM calls
    captured: dict = {}

    async def _mock_complete(system_prompt, user_message, agent_id, model=None):
        captured["system_prompt"] = system_prompt
        return ("test reply", "mock")

    mock_inference = MagicMock()
    mock_inference.complete = _mock_complete

    # 4. Real IdentityLoader + AgentRouter wired with orient cache
    identity_loader = IdentityLoader()
    router = AgentRouter(
        identity_loader, inference_client=mock_inference, orient_cache=orient_cache
    )

    # 5. Send a packet
    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="system",
        user_id="test-user",
        thread_id="integration-test-thread",
        agent_id="cypher",
        message="hello",
        metadata={},
    )
    reply = await router.route_and_process(packet)

    # 6. Assert the full roundtrip
    assert reply.status == "ok"
    assert "system_prompt" in captured, "inference was never called"
    assert "[SWARM STATE]" in captured["system_prompt"], (
        f"[SWARM STATE] block missing from system_prompt.\n"
        f"Got:\n{captured['system_prompt']}"
    )
    assert "toward integration clarity" in captured["system_prompt"], (
        "drift_vector not present in system_prompt"
    )


async def test_orient_inject_graceful_when_webmind_empty(webmind_app):
    """
    When WebMind has no limbic state, Brain should still reply normally.
    No [SWARM STATE] block injected, but no crash either.
    """
    webmind_client = _ASGIWebMindClient(webmind_app)
    orient_cache = OrientCache(webmind_client=webmind_client, ttl_seconds=300)

    captured: dict = {}

    async def _mock_complete(system_prompt, user_message, agent_id, model=None):
        captured["system_prompt"] = system_prompt
        return ("test reply", "mock")

    mock_inference = MagicMock()
    mock_inference.complete = _mock_complete

    identity_loader = IdentityLoader()
    router = AgentRouter(
        identity_loader, inference_client=mock_inference, orient_cache=orient_cache
    )

    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="system",
        user_id="test-user",
        thread_id="empty-webmind-thread",
        agent_id="cypher",
        message="hello",
        metadata={},
    )
    reply = await router.route_and_process(packet)

    assert reply.status == "ok"
    # No limbic state -- no inject, but no crash
    assert "[SWARM STATE]" not in captured.get("system_prompt", "")


async def test_orient_inject_webmind_offline():
    """
    When WebMind is completely offline (client returns None), Brain replies normally.
    """
    # OrientCache with no webmind client (offline simulation)
    orient_cache = OrientCache(webmind_client=None)

    captured: dict = {}

    async def _mock_complete(system_prompt, user_message, agent_id, model=None):
        captured["system_prompt"] = system_prompt
        return ("test reply", "mock")

    mock_inference = MagicMock()
    mock_inference.complete = _mock_complete

    identity_loader = IdentityLoader()
    router = AgentRouter(
        identity_loader, inference_client=mock_inference, orient_cache=orient_cache
    )

    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="system",
        user_id="test-user",
        thread_id="offline-webmind-thread",
        agent_id="drevan",
        message="hello",
        metadata={},
    )
    reply = await router.route_and_process(packet)

    assert reply.status == "ok"
    assert "[SWARM STATE]" not in captured.get("system_prompt", "")
