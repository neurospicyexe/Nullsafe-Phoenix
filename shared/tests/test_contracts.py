"""
Unit tests for shared contracts.

Tests cover:
- ThoughtPacket validation (UUID4, ISO-8601, metadata)
- AgentReply validation
- JSON serialization/deserialization
- QueueEnvelope functionality
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.contracts import AgentReply, QueueEnvelope, SwarmReply, ThoughtPacket


class TestThoughtPacket:
    """Test suite for ThoughtPacket validation."""

    def test_valid_discord_packet(self):
        """Test creating a valid Discord ThoughtPacket."""
        packet = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp="2026-01-17T20:00:00Z",
            source="discord",
            user_id="discord:123456789",
            thread_id="987654321",
            agent_id="cypher",
            message="Hello, agent!",
            metadata={
                "channel_id": "987654321",
                "guild_id": "111222333",
                "platform": "discord"
            }
        )

        # UUID validator normalizes the UUID
        assert packet.packet_id.startswith("123e4567-e89b-")
        assert packet.source == "discord"
        assert packet.agent_id == "cypher"
        assert packet.metadata["channel_id"] == "987654321"

    def test_valid_webui_packet(self):
        """Test creating a valid WebUI ThoughtPacket."""
        packet = ThoughtPacket(
            packet_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            timestamp="2026-01-17T20:00:00+00:00",
            source="webui",
            user_id="user_123",
            thread_id="session_abc123",
            agent_id="drevan",
            message="Test message",
            metadata={"session_id": "abc123"}
        )

        assert packet.source == "webui"
        assert packet.agent_id == "drevan"

    def test_invalid_packet_id_format(self):
        """Test that invalid UUID4 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtPacket(
                packet_id="not-a-valid-uuid",
                timestamp="2026-01-17T20:00:00Z",
                source="discord",
                user_id="user_123",
                thread_id="thread_123",
                agent_id="gaia",
                message="Test",
                metadata={"channel_id": "123"}
            )

        errors = exc_info.value.errors()
        assert any("packet_id" in str(e) for e in errors)

    def test_invalid_timestamp_format(self):
        """Test that invalid ISO-8601 timestamp is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtPacket(
                packet_id="123e4567-e89b-12d3-a456-426614174000",
                timestamp="2026/01/17 20:00:00",  # Wrong format
                source="discord",
                user_id="user_123",
                thread_id="thread_123",
                agent_id="cypher",
                message="Test",
                metadata={"channel_id": "123"}
            )

        errors = exc_info.value.errors()
        assert any("timestamp" in str(e) for e in errors)

    def test_discord_source_requires_channel_id(self):
        """Test that Discord source requires metadata.channel_id."""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtPacket(
                packet_id="123e4567-e89b-12d3-a456-426614174000",
                timestamp="2026-01-17T20:00:00Z",
                source="discord",
                user_id="user_123",
                thread_id="thread_123",
                agent_id="cypher",
                message="Test",
                metadata={"guild_id": "123"}  # Missing channel_id
            )

        errors = exc_info.value.errors()
        assert any("channel_id" in str(e) for e in errors)

    def test_webui_source_no_channel_id_required(self):
        """Test that WebUI source doesn't require channel_id."""
        packet = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp="2026-01-17T20:00:00Z",
            source="webui",
            user_id="user_123",
            thread_id="session_123",
            agent_id="drevan",
            message="Test",
            metadata={"session_id": "123"}  # No channel_id needed
        )

        assert packet.source == "webui"

    def test_invalid_agent_id(self):
        """Test that invalid agent_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtPacket(
                packet_id="123e4567-e89b-12d3-a456-426614174000",
                timestamp="2026-01-17T20:00:00Z",
                source="discord",
                user_id="user_123",
                thread_id="thread_123",
                agent_id="unknown_agent",  # Not in allowed list
                message="Test",
                metadata={"channel_id": "123"}
            )

        errors = exc_info.value.errors()
        assert any("agent_id" in str(e) for e in errors)

    def test_optional_fields_defaults(self):
        """Test that optional fields have correct defaults."""
        packet = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp="2026-01-17T20:00:00Z",
            source="discord",
            user_id="user_123",
            thread_id="thread_123",
            agent_id="cypher",
            message="Test",
            metadata={"channel_id": "123"}
        )

        assert packet.lane is None
        assert packet.policy_profile == "safe_default"
        assert packet.priority == 5
        assert packet.trace is None

    def test_json_serialization_roundtrip(self):
        """Test JSON serialization and deserialization."""
        original = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp="2026-01-17T20:00:00Z",
            source="discord",
            user_id="user_123",
            thread_id="thread_123",
            agent_id="cypher",
            message="Test message",
            metadata={"channel_id": "123", "platform": "discord"},
            lane="praxis",
            priority=7
        )

        # Serialize to JSON
        json_str = original.to_json()
        assert isinstance(json_str, str)

        # Deserialize back
        restored = ThoughtPacket.from_json(json_str)

        assert restored.packet_id == original.packet_id
        assert restored.message == original.message
        assert restored.lane == original.lane
        assert restored.priority == original.priority
        assert restored.metadata == original.metadata


class TestAgentReply:
    """Test suite for AgentReply validation."""

    def test_valid_ok_reply(self):
        """Test creating a valid successful AgentReply."""
        reply = AgentReply(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            agent_id="cypher",
            status="ok",
            reply_text="Here is my response."
        )

        # UUID validator normalizes the UUID
        assert reply.packet_id.startswith("123e4567-e89b-")
        assert reply.status == "ok"
        assert reply.reply_text == "Here is my response."

    def test_valid_queued_reply_empty_text(self):
        """Test that queued status can have empty reply_text."""
        reply = AgentReply(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            agent_id="drevan",
            status="queued",
            reply_text=""  # Empty is allowed for queued
        )

        assert reply.status == "queued"
        assert reply.reply_text == ""

    def test_invalid_packet_id(self):
        """Test that invalid UUID4 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AgentReply(
                packet_id="invalid-uuid",
                agent_id="gaia",
                status="ok",
                reply_text="Test"
            )

        errors = exc_info.value.errors()
        assert any("packet_id" in str(e) for e in errors)

    def test_invalid_status(self):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AgentReply(
                packet_id="123e4567-e89b-12d3-a456-426614174000",
                agent_id="cypher",
                status="invalid_status",  # Not in allowed list
                reply_text="Test"
            )

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)

    def test_optional_trace_and_writes(self):
        """Test optional trace and writes fields."""
        reply = AgentReply(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            agent_id="cypher",
            status="ok",
            reply_text="Response with trace",
            trace={"repro_stamp": "2026-01-17T20:00:00Z"},
            writes=[
                {"path": "Journals/Agents/test.md", "action": "append", "bytes": 123}
            ]
        )

        assert reply.trace is not None
        assert reply.trace["repro_stamp"] == "2026-01-17T20:00:00Z"
        assert len(reply.writes) == 1
        assert reply.writes[0]["action"] == "append"

    def test_json_serialization_roundtrip(self):
        """Test JSON serialization and deserialization."""
        original = AgentReply(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            agent_id="gaia",
            status="ok",
            reply_text="Test response",
            trace={"debug": "info"}
        )

        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)

        # Deserialize
        restored = AgentReply.from_json(json_str)

        assert restored.packet_id == original.packet_id
        assert restored.agent_id == original.agent_id
        assert restored.status == original.status
        assert restored.reply_text == original.reply_text
        assert restored.trace == original.trace


class TestQueueEnvelope:
    """Test suite for QueueEnvelope."""

    def test_valid_envelope_creation(self):
        """Test creating a valid queue envelope."""
        now = datetime.now(timezone.utc).isoformat()
        packet_dict = {
            "packet_id": "123e4567-e89b-12d3-a456-426614174000",
            "timestamp": now,
            "source": "discord",
            "user_id": "user_123",
            "thread_id": "thread_123",
            "agent_id": "cypher",
            "message": "Test",
            "metadata": {"channel_id": "123"}
        }

        envelope = QueueEnvelope(
            packet=packet_dict,
            attempts=0,
            first_attempt_ts=now,
            last_attempt_ts=now
        )

        assert envelope.attempts == 0
        assert envelope.packet["packet_id"] == "123e4567-e89b-12d3-a456-426614174000"

    def test_envelope_json_roundtrip(self):
        """Test envelope JSON serialization."""
        now = datetime.now(timezone.utc).isoformat()
        packet_dict = {
            "packet_id": "123e4567-e89b-12d3-a456-426614174000",
            "agent_id": "cypher",
            "status": "ok",
            "reply_text": "Response"
        }

        original = QueueEnvelope(
            packet=packet_dict,
            attempts=3,
            first_attempt_ts=now,
            last_attempt_ts=now
        )

        # Serialize
        json_str = original.to_json()

        # Deserialize
        restored = QueueEnvelope.from_json(json_str)

        assert restored.attempts == 3
        assert restored.packet == packet_dict


class TestContractIntegration:
    """Integration tests for contract interactions."""

    def test_thought_packet_to_agent_reply_flow(self):
        """Test typical packet → reply flow."""
        # Create request packet
        request = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp="2026-01-17T20:00:00Z",
            source="discord",
            user_id="user_123",
            thread_id="channel_123",
            agent_id="cypher",
            message="Test message",
            metadata={"channel_id": "channel_123"}
        )

        # Create reply with same packet_id
        reply = AgentReply(
            packet_id=request.packet_id,  # Echo back
            agent_id=request.agent_id,
            status="ok",
            reply_text="Processed your message"
        )

        assert reply.packet_id == request.packet_id
        assert reply.agent_id == request.agent_id

    def test_envelope_wrapping_thought_packet(self):
        """Test wrapping ThoughtPacket in envelope."""
        now = datetime.now(timezone.utc).isoformat()

        packet = ThoughtPacket(
            packet_id="123e4567-e89b-12d3-a456-426614174000",
            timestamp=now,
            source="discord",
            user_id="user_123",
            thread_id="thread_123",
            agent_id="drevan",
            message="Test",
            metadata={"channel_id": "123"}
        )

        # Wrap in envelope
        envelope = QueueEnvelope(
            packet=json.loads(packet.to_json()),
            attempts=0,
            first_attempt_ts=now,
            last_attempt_ts=now
        )

        # Verify envelope contains packet data
        assert envelope.packet["packet_id"] == packet.packet_id
        assert envelope.packet["message"] == packet.message

        # Simulate retry
        envelope.attempts += 1
        assert envelope.attempts == 1


def test_swarm_reply_valid():
    reply = SwarmReply(
        packet_id="550e8400-e29b-41d4-a716-446655440000",
        thread_id="ch123",
        responses={"drevan": "Hello", "cypher": None, "gaia": "Witness."},
        depth=0,
    )
    assert reply.responses["cypher"] is None
    assert reply.status == "ok"


def test_thought_packet_swarm_fields():
    import uuid, datetime
    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch1",
        agent_id="cypher",
        message="hello",
        metadata={"channel_id": "ch1"},
        author="Blue",
        author_is_companion=False,
        depth=1,
    )
    assert packet.author == "Blue"
    assert packet.depth == 1


def test_thought_packet_author_defaults():
    import uuid, datetime
    packet = ThoughtPacket(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch1",
        agent_id="cypher",
        message="hello",
        metadata={"channel_id": "ch1"},
    )
    assert packet.author == "Raziel"
    assert packet.author_is_companion is False
    assert packet.depth == 0
