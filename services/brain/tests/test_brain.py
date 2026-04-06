"""
Unit tests for Brain service.

Tests:
- Health endpoint
- Chat endpoint with ThoughtPacket
- Agent routing logic (thread mapping, overrides)
- Identity loading
"""

import sys
from pathlib import Path

# Add project root to path so we can import shared module
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from shared.contracts import ThoughtPacket, AgentReply
from services.brain.main import app

client = TestClient(app)


class TestHealthEndpoint:
    """Test suite for /health endpoint."""

    def test_health_check(self):
        """Test health endpoint returns OK."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "brain"
        assert data["version"] == "v2-day-one"
        assert "timestamp" in data


class TestChatEndpoint:
    """Test suite for /chat endpoint."""

    def test_chat_basic_packet(self):
        """Test processing a basic ThoughtPacket."""
        packet = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id="test_thread_123",
            agent_id="cypher",
            message="Hello, can you help me?",
            metadata={"channel_id": "channel_123"}
        )

        response = client.post("/chat", json=packet.model_dump())
        assert response.status_code == 200

        reply = AgentReply(**response.json())
        assert reply.packet_id == packet.packet_id
        assert reply.agent_id == "cypher"  # Should use packet agent_id initially
        assert reply.status == "ok"
        assert len(reply.reply_text) > 0
        assert "Cypher" in reply.reply_text  # Identity-aware
        assert "trace" in response.json()
        assert "repro_stamp" in response.json()["trace"]

    def test_chat_with_drevan_override(self):
        """Test override prefix routes to Drevan."""
        packet = ThoughtPacket(
            packet_id="223e4567-e89b-12d3-a456-426614174001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id="test_thread_456",
            agent_id="cypher",  # Original agent is Cypher
            message="Drevan: Help me organize my notes",
            metadata={"channel_id": "channel_456"}
        )

        response = client.post("/chat", json=packet.model_dump())
        assert response.status_code == 200

        reply = AgentReply(**response.json())
        assert reply.agent_id == "drevan"  # Override should route to Drevan
        assert "Drevan" in reply.reply_text
        # Message should be cleaned (prefix removed)
        assert "Help me organize my notes" in reply.reply_text

    def test_chat_with_gaia_override(self):
        """Test override prefix routes to Gaia."""
        packet = ThoughtPacket(
            packet_id="323e4567-e89b-12d3-a456-426614174002",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="webui",
            user_id="test_user",
            thread_id="session_789",
            agent_id="cypher",
            message="GAIA: What are the connections between quantum physics and consciousness?",
            metadata={"session_id": "abc123"}
        )

        response = client.post("/chat", json=packet.model_dump())
        assert response.status_code == 200

        reply = AgentReply(**response.json())
        assert reply.agent_id == "gaia"  # Override should route to Gaia
        assert "Gaia" in reply.reply_text

    def test_thread_routing_persistence(self):
        """Test that thread routing persists across messages."""
        thread_id = "persistent_thread_999"

        # First message to Cypher
        packet1 = ThoughtPacket(
            packet_id="423e4567-e89b-12d3-a456-426614174003",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id=thread_id,
            agent_id="cypher",
            message="First message",
            metadata={"channel_id": "channel_999"}
        )

        response1 = client.post("/chat", json=packet1.model_dump())
        assert response1.status_code == 200
        reply1 = AgentReply(**response1.json())
        assert reply1.agent_id == "cypher"

        # Second message - should route to Cypher via thread mapping
        packet2 = ThoughtPacket(
            packet_id="523e4567-e89b-12d3-a456-426614174004",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id=thread_id,  # Same thread
            agent_id="drevan",  # Different agent_id in packet
            message="Second message",
            metadata={"channel_id": "channel_999"}
        )

        response2 = client.post("/chat", json=packet2.model_dump())
        assert response2.status_code == 200
        reply2 = AgentReply(**response2.json())
        assert reply2.agent_id == "cypher"  # Should still be Cypher (thread mapping)

        # Override should update thread mapping
        packet3 = ThoughtPacket(
            packet_id="623e4567-e89b-12d3-a456-426614174005",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id=thread_id,
            agent_id="cypher",
            message="Drevan: Third message with override",
            metadata={"channel_id": "channel_999"}
        )

        response3 = client.post("/chat", json=packet3.model_dump())
        assert response3.status_code == 200
        reply3 = AgentReply(**response3.json())
        assert reply3.agent_id == "drevan"  # Override to Drevan

        # Fourth message should now route to Drevan
        packet4 = ThoughtPacket(
            packet_id="723e4567-e89b-12d3-a456-426614174006",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id=thread_id,
            agent_id="cypher",
            message="Fourth message",
            metadata={"channel_id": "channel_999"}
        )

        response4 = client.post("/chat", json=packet4.model_dump())
        assert response4.status_code == 200
        reply4 = AgentReply(**response4.json())
        assert reply4.agent_id == "drevan"  # Thread now mapped to Drevan

    def test_repro_stamp_includes_identity_version(self):
        """Test that repro_stamp includes identity version hash."""
        packet = ThoughtPacket(
            packet_id="823e4567-e89b-12d3-a456-426614174007",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="discord",
            user_id="test_user",
            thread_id="test_thread_identity",
            agent_id="gaia",
            message="Test identity versioning",
            metadata={"channel_id": "channel_123"}
        )

        response = client.post("/chat", json=packet.model_dump())
        assert response.status_code == 200

        data = response.json()
        repro_stamp = data["trace"]["repro_stamp"]

        # Verify repro_stamp structure
        assert repro_stamp["packet_id"] == packet.packet_id
        assert repro_stamp["agent_id"] == "gaia"
        assert "identity_version" in repro_stamp
        assert len(repro_stamp["identity_version"]) == 16  # SHA256 first 16 chars
        assert "timestamp" in repro_stamp
        assert "thread_routing" in repro_stamp


class TestBrainConfig:
    """Test suite for Brain service configuration."""

    def test_brain_config_has_halseth_url(self):
        """Test that Config has Halseth and WebMind integration attributes."""
        from services.brain.config import Config
        assert hasattr(Config, "HALSETH_URL")
        assert hasattr(Config, "HALSETH_ADMIN_SECRET")
        assert hasattr(Config, "WEBMIND_URL")
        assert hasattr(Config, "SYNTHESIS_INTERVAL")

    def test_synthesis_interval_default_is_1200(self):
        """Test that SYNTHESIS_INTERVAL defaults to 1200 seconds."""
        import os
        os.environ.pop("SYNTHESIS_INTERVAL", None)
        import importlib
        import services.brain.config as cfg_module
        importlib.reload(cfg_module)
        assert cfg_module.Config.SYNTHESIS_INTERVAL == 1200
