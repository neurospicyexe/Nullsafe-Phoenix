#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - VPS Relay Service

FastAPI service for buffering, retry, and queue management.
NEVER calls Discord API, NEVER loads identity, NEVER runs LLM inference.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.contracts import ThoughtPacket, AgentReply
from services.relay.config import Config
from services.relay.redis_client import RedisClient
from services.relay.brain_client import BrainClient
from services.relay.drainer import QueueDrainer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress verbose httpx and uvicorn access logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Initialize clients (will be connected in lifespan)
redis_client = RedisClient()
brain_client = BrainClient()
drainer = QueueDrainer(redis_client, brain_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown.

    Startup:
    - Connect to Redis
    - Connect Brain HTTP client
    - Start drainer background task

    Shutdown:
    - Stop drainer
    - Close connections
    """
    # Startup
    logger.info("Starting Relay service...")

    try:
        await redis_client.connect()
        await brain_client.connect()
        await drainer.start()

        logger.info("Relay service started successfully")
        logger.info("=" * 60)
        logger.info("RELAY CONFIGURATION:")
        logger.info(f"  Brain URL: {Config.BRAIN_SERVICE_URL}")
        # Hide password in Redis URL if present
        redis_display = Config.REDIS_URL.split('@')[-1] if '@' in Config.REDIS_URL else Config.REDIS_URL
        logger.info(f"  Redis URL: {redis_display}")
        logger.info(f"  Fast timeout: {Config.BRAIN_TIMEOUT_FAST}s")
        logger.info(f"  Drainer timeout: {Config.BRAIN_TIMEOUT_DRAINER}s")
        logger.info(f"  Drainer interval: {Config.DRAINER_INTERVAL}s")
        logger.info(f"  Max retries: {Config.MAX_RETRIES}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Failed to start Relay service: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down Relay service...")

    try:
        await drainer.stop()
        await brain_client.close()
        await redis_client.close()

        logger.info("Relay service shut down successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# Initialize FastAPI app
app = FastAPI(
    title="Nullsafe Phoenix Relay",
    version="v2-day-one",
    description="VPS Relay service for buffering and retry",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "relay",
        "version": "v2-day-one",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/status")
async def status():
    """
    Status endpoint exposing queue depths and Brain status.

    Returns:
        Dictionary with:
        - brain_status: "online" or "offline"
        - queue_lengths: incoming, inflight, deadletter, outbox counts
        - timestamp: Current timestamp
    """
    brain_status = await redis_client.get_brain_status()
    queue_lengths = await redis_client.get_queue_lengths()

    return {
        "brain_status": brain_status,
        "queue_lengths": queue_lengths,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/ingest")
async def ingest(packet: ThoughtPacket) -> AgentReply:
    """
    Ingest ThoughtPacket with fast path and queueing.

    Flow:
    1. Validate ThoughtPacket (Pydantic handles this)
    2. Check dedupe: if already processed, return safe duplicate response
    3. Mark as ingested (dedupe with TTL)
    4. Fast path: Try forwarding to Brain with 5s timeout
    5. On success: Return AgentReply with status="ok"
    6. On failure: Enqueue to Redis, return AgentReply with status="queued"

    Args:
        packet: ThoughtPacket to ingest

    Returns:
        AgentReply indicating processing result
    """
    packet_id = packet.packet_id

    logger.info(
        f"Ingesting packet {packet_id} from {packet.source} "
        f"(thread: {packet.thread_id}, agent: {packet.agent_id})"
    )

    try:
        # Check dedupe
        already_processed = await redis_client.check_dedupe_ingest(packet_id)

        if already_processed:
            logger.info(
                f"Packet {packet_id} already processed (dedupe), "
                f"returning duplicate-accepted response"
            )

            return AgentReply(
                packet_id=packet_id,
                agent_id=packet.agent_id,
                status="queued",
                reply_text="",  # Empty for dedupe
                trace={
                    "dedupe": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

        # Mark as ingested
        await redis_client.mark_dedupe_ingest(packet_id)

        # Fast path: Try forwarding to Brain immediately
        logger.debug(f"Attempting fast path for packet {packet_id}")

        reply = await brain_client.send_packet(
            packet,
            timeout=Config.BRAIN_TIMEOUT_FAST
        )

        if reply and reply.status == "ok":
            # Fast path success!
            logger.info(
                f"Fast path success for packet {packet_id} "
                f"(agent: {reply.agent_id})"
            )

            # Emit to outbox with dedupe check
            await _emit_to_outbox_safe(packet, reply)

            return reply

        else:
            # Fast path failed, enqueue for retry
            logger.info(
                f"Fast path failed for packet {packet_id}, enqueueing"
            )

            await redis_client.enqueue_incoming(packet.model_dump())

            return AgentReply(
                packet_id=packet_id,
                agent_id=packet.agent_id,
                status="queued",
                reply_text="",
                trace={
                    "queued": True,
                    "reason": "brain_timeout_or_offline",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

    except Exception as e:
        logger.error(
            f"Error ingesting packet {packet_id}: {e}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing packet: {str(e)}"
        )


async def _emit_to_outbox_safe(packet: ThoughtPacket, reply: AgentReply):
    """
    Emit reply to outbox with dedupe check (used by fast path).

    Args:
        packet: Original ThoughtPacket
        reply: AgentReply from Brain
    """
    packet_id = packet.packet_id

    # Check dedupe
    already_sent = await redis_client.check_dedupe_outbox(packet_id)

    if already_sent:
        logger.info(
            f"Reply for packet {packet_id} already in outbox (dedupe), skipping"
        )
        return

    # Mark as sent
    await redis_client.mark_dedupe_outbox(packet_id)

    # Extract channel_id from metadata
    channel_id = packet.metadata.get("channel_id", packet.thread_id)

    # Create outbox event
    outbox_event = {
        "packet_id": packet_id,
        "agent_id": reply.agent_id,
        "thread_id": packet.thread_id,
        "channel_id": channel_id,
        "reply_text": reply.reply_text,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Enqueue to per-agent outbox
    await redis_client.enqueue_outbox(outbox_event, reply.agent_id)

    logger.info(
        f"Emitted reply for packet {packet_id} to outbox (channel: {channel_id})"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
