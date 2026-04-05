"""
Unit tests for Discord bot.

Tests:
- Redis client operations (dedupe, queue operations)
- Relay client (ingest packet)
- Outbox consumer (dedupe, retry, deadletter)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import respx
from datetime import datetime, timezone
from httpx import Response
from fakeredis import aioredis as fake_aioredis

from shared.contracts import ThoughtPacket, AgentReply
from services.discord_bot.redis_client import DiscordRedisClient
from services.discord_bot.relay_client import RelayClient
from services.discord_bot.config import Config


@pytest.fixture
async def redis_client():
    """Create Discord Redis client with fake Redis."""
    client = DiscordRedisClient()
    client._redis = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def relay_client():
    """Create Relay HTTP client."""
    client = RelayClient()
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
def sample_packet():
    """Create sample ThoughtPacket."""
    return ThoughtPacket(
        packet_id="123e4567-e89b-12d3-a456-426614174000",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="discord",
        user_id="discord:123456789",
        thread_id="987654321",
        agent_id="cypher",
        message="Hello from Discord",
        metadata={
            "channel_id": "987654321",
            "guild_id": "111222333",
            "platform": "discord"
        }
    )


@pytest.fixture
def sample_reply():
    """Create sample AgentReply."""
    return AgentReply(
        packet_id="123e4567-e89b-12d3-a456-426614174000",
        agent_id="cypher",
        status="ok",
        reply_text="Test reply from agent"
    )


@pytest.fixture
def sample_outbox_event():
    """Create sample outbox event."""
    return {
        "packet_id": "123e4567-e89b-12d3-a456-426614174000",
        "agent_id": "cypher",
        "thread_id": "987654321",
        "channel_id": "987654321",
        "reply_text": "Test reply",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


class TestDiscordRedisClient:
    """Test suite for Discord Redis client operations."""

    @pytest.mark.asyncio
    async def test_dequeue_outbox_to_inflight(self, redis_client, sample_outbox_event):
        """Test dequeuing from outbox to inflight."""
        import json

        # Add event to outbox
        event_json = json.dumps(sample_outbox_event)
        await redis_client._redis.lpush(Config.OUTBOX_QUEUE, event_json)

        # Dequeue to inflight
        dequeued = await redis_client.dequeue_outbox_to_inflight()

        assert dequeued is not None
        assert dequeued["packet_id"] == sample_outbox_event["packet_id"]

        # Check queue lengths
        outbox_len = await redis_client._redis.llen(Config.OUTBOX_QUEUE)
        inflight_len = await redis_client._redis.llen(Config.OUTBOX_INFLIGHT)

        assert outbox_len == 0
        assert inflight_len == 1

    @pytest.mark.asyncio
    async def test_remove_from_inflight(self, redis_client, sample_outbox_event):
        """Test removing event from inflight queue."""
        import json

        # Add to outbox and move to inflight
        event_json = json.dumps(sample_outbox_event)
        await redis_client._redis.lpush(Config.OUTBOX_QUEUE, event_json)
        await redis_client.dequeue_outbox_to_inflight()

        # Remove from inflight
        await redis_client.remove_from_inflight(sample_outbox_event)

        # Check queue length
        inflight_len = await redis_client._redis.llen(Config.OUTBOX_INFLIGHT)
        assert inflight_len == 0

    @pytest.mark.asyncio
    async def test_move_to_deadletter(self, redis_client, sample_outbox_event):
        """Test moving event to deadletter queue."""
        await redis_client.move_to_deadletter(sample_outbox_event)

        deadletter_len = await redis_client._redis.llen(Config.OUTBOX_DEADLETTER)
        assert deadletter_len == 1

    @pytest.mark.asyncio
    async def test_check_already_sent(self, redis_client):
        """Test checking if packet already sent."""
        packet_id = "test-packet-123"

        # Initially not sent
        sent = await redis_client.check_already_sent(packet_id)
        assert sent is False

        # Mark as sent
        await redis_client.mark_as_sent(packet_id)

        # Now should be marked
        sent = await redis_client.check_already_sent(packet_id)
        assert sent is True

    @pytest.mark.asyncio
    async def test_get_queue_lengths(self, redis_client, sample_outbox_event):
        """Test getting queue lengths."""
        import json

        # Add events to queues
        event_json = json.dumps(sample_outbox_event)
        await redis_client._redis.lpush(Config.OUTBOX_QUEUE, event_json)
        await redis_client._redis.lpush(Config.OUTBOX_INFLIGHT, event_json)
        await redis_client._redis.lpush(Config.OUTBOX_DEADLETTER, event_json)

        lengths = await redis_client.get_queue_lengths()

        assert lengths["outbox"] == 1
        assert lengths["inflight"] == 1
        assert lengths["deadletter"] == 1


class TestRelayClient:
    """Test suite for Relay HTTP client."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_ingest_packet_success(self, relay_client, sample_packet, sample_reply):
        """Test successful packet ingestion."""
        # Mock Relay /ingest endpoint
        respx.post(f"{Config.RELAY_API_URL}/ingest").mock(
            return_value=Response(200, json=sample_reply.model_dump())
        )

        reply = await relay_client.ingest_packet(sample_packet)

        assert reply is not None
        assert reply.packet_id == sample_packet.packet_id
        assert reply.status == "ok"

    @pytest.mark.asyncio
    @respx.mock
    async def test_ingest_packet_queued(self, relay_client, sample_packet):
        """Test packet queued response."""
        queued_reply = AgentReply(
            packet_id=sample_packet.packet_id,
            agent_id=sample_packet.agent_id,
            status="queued",
            reply_text=""
        )

        # Mock Relay /ingest endpoint
        respx.post(f"{Config.RELAY_API_URL}/ingest").mock(
            return_value=Response(200, json=queued_reply.model_dump())
        )

        reply = await relay_client.ingest_packet(sample_packet)

        assert reply is not None
        assert reply.status == "queued"

    @pytest.mark.asyncio
    @respx.mock
    async def test_ingest_packet_timeout(self, relay_client, sample_packet):
        """Test Relay timeout returns None."""
        # Mock Relay /ingest endpoint with timeout
        respx.post(f"{Config.RELAY_API_URL}/ingest").mock(
            side_effect=Exception("Timeout")
        )

        reply = await relay_client.ingest_packet(sample_packet)

        assert reply is None


class TestOutboxConsumer:
    """Test suite for outbox consumer logic."""

    # Note: Full outbox consumer tests would require mocking Discord client
    # For Day One, we've tested the core Redis operations above

    pass


@pytest.mark.asyncio
class TestDiscordBotIntegration:
    """Integration tests for Discord bot."""

    # Note: Full integration tests would require mocking discord.py
    # For Day One, we've tested the core components above

    pass
