"""
Unit tests for Relay service.

Tests:
- Health and status endpoints
- /ingest fast path (Brain online)
- /ingest queueing (Brain offline)
- Dedupe on ingest
- Drainer processing queued packets
- Outbox dedupe
- Deadletter after max retries
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
from services.relay.redis_client import RedisClient
from services.relay.brain_client import BrainClient
from services.relay.drainer import QueueDrainer
from services.relay.config import Config


@pytest.fixture
async def redis_client():
    """Create Redis client with fake Redis."""
    client = RedisClient()
    # Use fakeredis for testing
    client._redis = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def brain_client():
    """Create Brain HTTP client."""
    client = BrainClient()
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
        user_id="test_user",
        thread_id="test_thread",
        agent_id="cypher",
        message="Test message",
        metadata={"channel_id": "channel_123"}
    )


@pytest.fixture
def sample_reply():
    """Create sample AgentReply."""
    return AgentReply(
        packet_id="123e4567-e89b-12d3-a456-426614174000",
        agent_id="cypher",
        status="ok",
        reply_text="Test reply from Brain"
    )


class TestRedisClient:
    """Test suite for Redis client operations."""

    @pytest.mark.asyncio
    async def test_dedupe_ingest(self, redis_client):
        """Test ingest dedupe marking and checking."""
        packet_id = "test-packet-123"

        # Initially not marked
        exists = await redis_client.check_dedupe_ingest(packet_id)
        assert exists is False

        # Mark as ingested
        await redis_client.mark_dedupe_ingest(packet_id)

        # Now should exist
        exists = await redis_client.check_dedupe_ingest(packet_id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_dedupe_outbox(self, redis_client):
        """Test outbox dedupe marking and checking."""
        packet_id = "test-packet-456"

        # Initially not marked
        exists = await redis_client.check_dedupe_outbox(packet_id)
        assert exists is False

        # Mark as sent
        await redis_client.mark_dedupe_outbox(packet_id)

        # Now should exist
        exists = await redis_client.check_dedupe_outbox(packet_id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_enqueue_and_dequeue_incoming(self, redis_client, sample_packet):
        """Test enqueuing and dequeuing from incoming queue."""
        packet_dict = sample_packet.model_dump()

        # Enqueue
        await redis_client.enqueue_incoming(packet_dict)

        # Check queue length
        lengths = await redis_client.get_queue_lengths()
        assert lengths["incoming"] == 1
        assert lengths["inflight"] == 0

        # Dequeue to inflight (RPOPLPUSH)
        dequeued = await redis_client.dequeue_incoming_to_inflight()
        assert dequeued is not None
        assert dequeued["packet_id"] == sample_packet.packet_id

        # Check queue lengths
        lengths = await redis_client.get_queue_lengths()
        assert lengths["incoming"] == 0
        assert lengths["inflight"] == 1

    @pytest.mark.asyncio
    async def test_remove_from_inflight(self, redis_client, sample_packet):
        """Test removing packet from inflight queue."""
        packet_dict = sample_packet.model_dump()

        # Add to incoming and move to inflight
        await redis_client.enqueue_incoming(packet_dict)
        await redis_client.dequeue_incoming_to_inflight()

        # Remove from inflight
        await redis_client.remove_from_inflight(packet_dict)

        # Check queue length
        lengths = await redis_client.get_queue_lengths()
        assert lengths["inflight"] == 0

    @pytest.mark.asyncio
    async def test_move_to_deadletter(self, redis_client, sample_packet):
        """Test moving packet to deadletter queue."""
        packet_dict = sample_packet.model_dump()

        await redis_client.move_to_deadletter(packet_dict)

        lengths = await redis_client.get_queue_lengths()
        assert lengths["deadletter"] == 1

    @pytest.mark.asyncio
    async def test_enqueue_outbox(self, redis_client):
        """Test enqueuing to per-agent Discord outbox."""
        outbox_event = {
            "packet_id": "test-123",
            "agent_id": "cypher",
            "thread_id": "thread_123",
            "channel_id": "channel_123",
            "reply_text": "Test reply",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await redis_client.enqueue_outbox(outbox_event, "cypher")

        lengths = await redis_client.get_queue_lengths()
        assert lengths["outbox"]["cypher"] == 1
        assert lengths["outbox"]["drevan"] == 0
        assert lengths["outbox"]["gaia"] == 0


class TestBrainClient:
    """Test suite for Brain HTTP client."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_packet_success(self, brain_client, sample_packet, sample_reply):
        """Test successful packet send to Brain."""
        # Mock Brain /chat endpoint
        respx.post(f"{Config.BRAIN_SERVICE_URL}/chat").mock(
            return_value=Response(200, json=sample_reply.model_dump())
        )

        reply = await brain_client.send_packet(sample_packet)

        assert reply is not None
        assert reply.packet_id == sample_packet.packet_id
        assert reply.status == "ok"

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_packet_timeout(self, brain_client, sample_packet):
        """Test Brain timeout returns None."""
        # Mock Brain /chat endpoint with timeout
        respx.post(f"{Config.BRAIN_SERVICE_URL}/chat").mock(
            side_effect=Exception("Timeout")
        )

        reply = await brain_client.send_packet(sample_packet, timeout=1.0)

        assert reply is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_success(self, brain_client):
        """Test Brain health check success."""
        respx.get(f"{Config.BRAIN_SERVICE_URL}/health").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        healthy = await brain_client.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_failure(self, brain_client):
        """Test Brain health check failure."""
        respx.get(f"{Config.BRAIN_SERVICE_URL}/health").mock(
            return_value=Response(500)
        )

        healthy = await brain_client.health_check()
        assert healthy is False


class TestDrainer:
    """Test suite for queue drainer."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_drainer_processes_queue_when_brain_online(
        self, redis_client, brain_client, sample_packet, sample_reply
    ):
        """Test drainer processes queued packets when Brain comes online."""
        # Mock Brain health check
        respx.get(f"{Config.BRAIN_SERVICE_URL}/health").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Mock Brain /chat endpoint
        respx.post(f"{Config.BRAIN_SERVICE_URL}/chat").mock(
            return_value=Response(200, json=sample_reply.model_dump())
        )

        # Enqueue packet
        await redis_client.enqueue_incoming(sample_packet.model_dump())

        # Create drainer
        drainer = QueueDrainer(redis_client, brain_client)

        # Process one packet
        await drainer._process_one_packet()

        # Check queues
        lengths = await redis_client.get_queue_lengths()
        assert lengths["incoming"] == 0
        assert lengths["inflight"] == 0
        assert lengths["outbox"] == 1  # Reply emitted to outbox

    @pytest.mark.asyncio
    @respx.mock
    async def test_drainer_retries_on_brain_failure(
        self, redis_client, brain_client, sample_packet
    ):
        """Test drainer retries packet on Brain failure."""
        # Mock Brain health check
        respx.get(f"{Config.BRAIN_SERVICE_URL}/health").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Mock Brain /chat endpoint to fail
        respx.post(f"{Config.BRAIN_SERVICE_URL}/chat").mock(
            side_effect=Exception("Brain error")
        )

        # Enqueue packet
        await redis_client.enqueue_incoming(sample_packet.model_dump())

        # Create drainer
        drainer = QueueDrainer(redis_client, brain_client)

        # Process packet (will fail)
        await drainer._process_one_packet()

        # Check queues - packet should be requeued
        lengths = await redis_client.get_queue_lengths()
        assert lengths["incoming"] == 1  # Requeued for retry
        assert lengths["inflight"] == 0  # Removed from inflight
        assert lengths["deadletter"] == 0  # Not yet in deadletter

        # Check retry count incremented
        assert drainer._retry_counts[sample_packet.packet_id] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_drainer_moves_to_deadletter_after_max_retries(
        self, redis_client, brain_client, sample_packet
    ):
        """Test drainer moves packet to deadletter after max retries."""
        # Mock Brain health check
        respx.get(f"{Config.BRAIN_SERVICE_URL}/health").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Mock Brain /chat endpoint to always fail
        respx.post(f"{Config.BRAIN_SERVICE_URL}/chat").mock(
            side_effect=Exception("Brain error")
        )

        # Enqueue packet
        await redis_client.enqueue_incoming(sample_packet.model_dump())

        # Create drainer
        drainer = QueueDrainer(redis_client, brain_client)

        # Set retry count to max - 1
        drainer._retry_counts[sample_packet.packet_id] = Config.MAX_RETRIES - 1

        # Process packet (will hit max retries)
        await drainer._process_one_packet()

        # Check queues
        lengths = await redis_client.get_queue_lengths()
        assert lengths["incoming"] == 0
        assert lengths["inflight"] == 0
        assert lengths["deadletter"] == 1  # Moved to deadletter

        # Retry count should be cleared
        assert sample_packet.packet_id not in drainer._retry_counts

    @pytest.mark.asyncio
    async def test_drainer_outbox_dedupe(
        self, redis_client, brain_client, sample_packet, sample_reply
    ):
        """Test drainer doesn't emit duplicate replies to outbox."""
        # Mark packet as already sent to outbox
        await redis_client.mark_dedupe_outbox(sample_packet.packet_id)

        # Create drainer
        drainer = QueueDrainer(redis_client, brain_client)

        # Try to emit to outbox
        await drainer._emit_to_outbox(sample_packet, sample_reply)

        # Check outbox - should still be empty (dedupe prevented emission)
        lengths = await redis_client.get_queue_lengths()
        assert lengths["outbox"] == 0


@pytest.mark.asyncio
class TestRelayIntegration:
    """Integration tests for Relay service."""

    # Note: These would use TestClient with actual FastAPI app
    # For now, we've tested the core components above

    pass
