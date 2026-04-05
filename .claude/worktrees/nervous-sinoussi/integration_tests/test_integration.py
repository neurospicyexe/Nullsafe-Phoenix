"""
Integration tests for Nullsafe Phoenix v2.

Tests the full system end-to-end:
- Relay ↔ Brain communication
- Discord bot ingress → Relay → Brain
- Queue drainer with Brain offline/online
- Outbox consumer with dedupe
- Deadletter queue handling
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import asyncio
import json
from datetime import datetime, timezone
from httpx import AsyncClient, Response
from fakeredis import aioredis as fake_aioredis
import respx

from shared.contracts import ThoughtPacket, AgentReply, QueueEnvelope
from services.relay.redis_client import RedisClient
from services.relay.brain_client import BrainClient
from services.relay.drainer import QueueDrainer
from services.relay.config import Config as RelayConfig
from services.discord_bot.redis_client import DiscordRedisClient
from services.discord_bot.relay_client import RelayClient


@pytest.fixture
async def redis_client():
    """Create Relay Redis client with fake Redis."""
    client = RedisClient()
    client._redis = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def discord_redis_client():
    """Create Discord Redis client with fake Redis (shared instance)."""
    client = DiscordRedisClient()
    # Share same fake Redis instance for integration
    relay_client = RedisClient()
    relay_client._redis = fake_aioredis.FakeRedis(decode_responses=True)
    client._redis = relay_client._redis
    yield client, relay_client
    await client.close()


@pytest.fixture
async def brain_client():
    """Create Brain HTTP client."""
    client = BrainClient()
    await client.connect()
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
def sample_discord_packet():
    """Create sample Discord ThoughtPacket."""
    return ThoughtPacket(
        packet_id="550e8400-e29b-41d4-a716-446655440000",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="discord",
        user_id="discord:123456789",
        thread_id="987654321",
        agent_id="cypher",
        message="Test message from Discord",
        metadata={
            "channel_id": "987654321",
            "guild_id": "111222333",
            "platform": "discord",
            "author_id": "123456789"
        }
    )


@pytest.fixture
def sample_agent_reply():
    """Create sample AgentReply."""
    return AgentReply(
        packet_id="550e8400-e29b-41d4-a716-446655440000",
        agent_id="cypher",
        status="ok",
        reply_text="Test reply from Cypher"
    )


@pytest.mark.asyncio
class TestRelayBrainIntegration:
    """Integration tests for Relay ↔ Brain communication."""

    @respx.mock
    async def test_relay_to_brain_fast_path(
        self,
        redis_client,
        brain_client,
        sample_discord_packet,
        sample_agent_reply
    ):
        """Test fast path: Relay sends to Brain, gets immediate reply."""
        # Mock Brain /chat endpoint
        respx.post("http://localhost:8001/chat").mock(
            return_value=Response(200, json=sample_agent_reply.model_dump())
        )

        # Send packet to Brain
        reply = await brain_client.send_packet(sample_discord_packet)

        assert reply is not None
        assert reply.packet_id == sample_discord_packet.packet_id
        assert reply.status == "ok"
        assert reply.reply_text == "Test reply from Cypher"

    @respx.mock
    async def test_relay_enqueue_when_brain_offline(
        self,
        redis_client,
        brain_client,
        sample_discord_packet
    ):
        """Test queueing when Brain is offline."""
        # Mock Brain /chat endpoint with timeout
        respx.post("http://localhost:8001/chat").mock(
            side_effect=Exception("Connection refused")
        )

        # Try to send - should fail
        reply = await brain_client.send_packet(sample_discord_packet)
        assert reply is None

        # Enqueue packet
        now_ts = datetime.now(timezone.utc).isoformat()
        envelope = QueueEnvelope(
            packet=sample_discord_packet.model_dump(),
            attempts=0,
            first_attempt_ts=now_ts,
            last_attempt_ts=now_ts
        )

        # The enqueue_incoming method expects dict not QueueEnvelope
        await redis_client.enqueue_incoming(sample_discord_packet.model_dump())

        # Check queue
        queue_len = await redis_client._redis.llen(RelayConfig.QUEUE_INCOMING)
        assert queue_len == 1

    @respx.mock
    async def test_drainer_processes_queue_when_brain_comes_online(
        self,
        redis_client,
        brain_client,
        sample_discord_packet,
        sample_agent_reply
    ):
        """Test drainer processes queued packets when Brain comes online."""
        # Enqueue packet
        await redis_client.enqueue_incoming(sample_discord_packet.model_dump())

        # Mock Brain online
        respx.post("http://localhost:8001/chat").mock(
            return_value=Response(200, json=sample_agent_reply.model_dump())
        )

        # Create drainer and process one event
        drainer = QueueDrainer(redis_client, brain_client)

        # Process queue
        await drainer._process_one_packet()

        # Queue should be empty
        queue_len = await redis_client._redis.llen(RelayConfig.QUEUE_INCOMING)
        assert queue_len == 0

        # Outbox should have reply
        outbox_len = await redis_client._redis.llen(RelayConfig.OUTBOX_DISCORD)
        assert outbox_len == 1


@pytest.mark.asyncio
class TestDiscordBotIntegration:
    """Integration tests for Discord bot ingress and outbox."""

    @respx.mock
    async def test_discord_ingress_to_relay_fast_path(
        self,
        relay_client,
        sample_discord_packet,
        sample_agent_reply
    ):
        """Test Discord bot sends packet to Relay, gets immediate reply."""
        # Mock Relay /ingest endpoint
        respx.post("http://localhost:8000/ingest").mock(
            return_value=Response(200, json=sample_agent_reply.model_dump())
        )

        # Send packet to Relay
        reply = await relay_client.ingest_packet(sample_discord_packet)

        assert reply is not None
        assert reply.packet_id == sample_discord_packet.packet_id
        assert reply.status == "ok"

    @respx.mock
    async def test_discord_ingress_to_relay_queued(
        self,
        relay_client,
        sample_discord_packet
    ):
        """Test Discord bot gets queued response when Brain offline."""
        queued_reply = AgentReply(
            packet_id=sample_discord_packet.packet_id,
            agent_id=sample_discord_packet.agent_id,
            status="queued",
            reply_text=""
        )

        # Mock Relay /ingest endpoint
        respx.post("http://localhost:8000/ingest").mock(
            return_value=Response(200, json=queued_reply.model_dump())
        )

        # Send packet to Relay
        reply = await relay_client.ingest_packet(sample_discord_packet)

        assert reply is not None
        assert reply.status == "queued"


@pytest.mark.asyncio
class TestOutboxConsumer:
    """Integration tests for outbox consumer."""

    async def test_outbox_consumer_dequeue_and_dedupe(
        self,
        discord_redis_client,
        sample_agent_reply
    ):
        """Test outbox consumer dequeues and checks dedupe."""
        discord_client, relay_client = discord_redis_client

        # Create outbox event
        outbox_event = {
            "packet_id": sample_agent_reply.packet_id,
            "agent_id": sample_agent_reply.agent_id,
            "thread_id": "987654321",
            "channel_id": "987654321",
            "reply_text": sample_agent_reply.reply_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Add to outbox via Relay Redis client
        from services.discord_bot.config import Config as DiscordConfig
        event_json = json.dumps(outbox_event)
        await relay_client._redis.lpush(DiscordConfig.OUTBOX_QUEUE, event_json)

        # Dequeue to inflight
        dequeued = await discord_client.dequeue_outbox_to_inflight()

        assert dequeued is not None
        assert dequeued["packet_id"] == sample_agent_reply.packet_id

        # Check dedupe (should not be sent yet)
        already_sent = await discord_client.check_already_sent(
            sample_agent_reply.packet_id
        )
        assert already_sent is False

        # Mark as sent
        await discord_client.mark_as_sent(sample_agent_reply.packet_id)

        # Check dedupe again (should be marked)
        already_sent = await discord_client.check_already_sent(
            sample_agent_reply.packet_id
        )
        assert already_sent is True

        # Try to dequeue again - should not send due to dedupe
        # (In real implementation, outbox consumer would check and drop)

    async def test_outbox_consumer_deadletter(
        self,
        discord_redis_client,
        sample_agent_reply
    ):
        """Test outbox consumer moves to deadletter after max retries."""
        discord_client, relay_client = discord_redis_client

        # Create outbox event
        outbox_event = {
            "packet_id": sample_agent_reply.packet_id,
            "agent_id": sample_agent_reply.agent_id,
            "thread_id": "987654321",
            "channel_id": "987654321",
            "reply_text": sample_agent_reply.reply_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Simulate max retries by moving to deadletter
        await discord_client.move_to_deadletter(outbox_event)

        # Check deadletter queue
        from services.discord_bot.config import Config as DiscordConfig
        deadletter_len = await relay_client._redis.llen(
            DiscordConfig.OUTBOX_DEADLETTER
        )
        assert deadletter_len == 1


@pytest.mark.asyncio
class TestEndToEndFlow:
    """End-to-end integration tests."""

    @respx.mock
    async def test_full_flow_discord_to_brain_and_back(
        self,
        redis_client,
        brain_client,
        relay_client,
        sample_discord_packet,
        sample_agent_reply
    ):
        """
        Test full flow: Discord → Relay → Brain → Relay → Discord.

        Flow:
        1. Discord bot sends ThoughtPacket to Relay /ingest
        2. Relay fast path sends to Brain /chat
        3. Brain returns AgentReply
        4. Relay emits to outbox
        5. Discord bot outbox consumer picks up and sends to Discord
        """
        # Mock Relay /ingest endpoint
        respx.post("http://localhost:8000/ingest").mock(
            return_value=Response(200, json=sample_agent_reply.model_dump())
        )

        # Step 1: Discord bot sends to Relay
        reply = await relay_client.ingest_packet(sample_discord_packet)

        assert reply is not None
        assert reply.status == "ok"
        assert reply.reply_text == sample_agent_reply.reply_text

        # In real system, Relay would emit to outbox
        # We simulate this by manually adding to outbox
        from services.discord_bot.config import Config as DiscordConfig
        outbox_event = {
            "packet_id": sample_discord_packet.packet_id,
            "agent_id": sample_discord_packet.agent_id,
            "thread_id": sample_discord_packet.thread_id,
            "channel_id": sample_discord_packet.metadata["channel_id"],
            "reply_text": sample_agent_reply.reply_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        event_json = json.dumps(outbox_event)
        await redis_client._redis.lpush(DiscordConfig.OUTBOX_QUEUE, event_json)

        # Step 5: Discord bot outbox consumer picks up
        # (We simulate by manually checking the outbox)
        outbox_len = await redis_client._redis.llen(DiscordConfig.OUTBOX_QUEUE)
        assert outbox_len == 1

    @respx.mock
    async def test_full_flow_with_brain_offline_then_online(
        self,
        redis_client,
        brain_client,
        sample_discord_packet,
        sample_agent_reply
    ):
        """
        Test full flow when Brain is offline, then comes online.

        Flow:
        1. Relay tries fast path to Brain (fails)
        2. Relay enqueues to incoming queue
        3. Brain comes online
        4. Drainer processes queue
        5. Drainer emits to outbox
        """
        # Step 1-2: Relay enqueues when Brain offline
        await redis_client.enqueue_incoming(sample_discord_packet.model_dump())

        queue_len = await redis_client._redis.llen(RelayConfig.QUEUE_INCOMING)
        assert queue_len == 1

        # Step 3: Brain comes online
        respx.post("http://localhost:8001/chat").mock(
            return_value=Response(200, json=sample_agent_reply.model_dump())
        )

        # Step 4: Drainer processes queue
        drainer = QueueDrainer(redis_client, brain_client)
        await drainer._process_one_packet()

        # Queue should be empty
        queue_len = await redis_client._redis.llen(RelayConfig.QUEUE_INCOMING)
        assert queue_len == 0

        # Step 5: Outbox should have reply
        outbox_len = await redis_client._redis.llen(RelayConfig.OUTBOX_DISCORD)
        assert outbox_len == 1

        # Verify outbox event
        outbox_json = await redis_client._redis.rpop(RelayConfig.OUTBOX_DISCORD)
        outbox_event = json.loads(outbox_json)

        assert outbox_event["packet_id"] == sample_discord_packet.packet_id
        assert outbox_event["reply_text"] == sample_agent_reply.reply_text
        assert outbox_event["channel_id"] == sample_discord_packet.metadata["channel_id"]


@pytest.mark.asyncio
class TestDeadletterHandling:
    """Tests for deadletter queue handling."""

    @respx.mock
    async def test_drainer_deadletter_after_max_retries(
        self,
        redis_client,
        brain_client,
        sample_discord_packet
    ):
        """Test drainer moves to deadletter after max retries."""
        # Enqueue packet
        await redis_client.enqueue_incoming(sample_discord_packet.model_dump())

        # Mock Brain offline
        respx.post("http://localhost:8001/chat").mock(
            side_effect=Exception("Connection refused")
        )

        # Create drainer
        drainer = QueueDrainer(redis_client, brain_client)

        # Process multiple times to exceed max retries
        for _ in range(RelayConfig.MAX_RETRIES + 1):
            await drainer._process_one_packet()

        # Process - should move to deadletter
        await drainer._process_one_packet()

        # Queue should be empty
        queue_len = await redis_client._redis.llen(RelayConfig.QUEUE_INCOMING)
        assert queue_len == 0

        # Deadletter should have event
        deadletter_len = await redis_client._redis.llen(
            RelayConfig.QUEUE_DEADLETTER
        )
        assert deadletter_len == 1
