#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis client wrapper for Relay service.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis

from services.relay.config import Config

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for queue and dedupe operations."""

    def __init__(self):
        """Initialize Redis client (connection created on first use)."""
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = await redis.from_url(
                Config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Connected to Redis at {Config.REDIS_URL}")

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    async def check_dedupe_ingest(self, packet_id: str) -> bool:
        """
        Check if packet has already been ingested.

        Returns:
            True if packet already processed, False otherwise
        """
        key = Config.get_dedupe_ingest_key(packet_id)
        exists = await self._redis.exists(key)
        return bool(exists)

    async def mark_dedupe_ingest(self, packet_id: str):
        """Mark packet as ingested with TTL."""
        key = Config.get_dedupe_ingest_key(packet_id)
        await self._redis.setex(key, Config.DEDUPE_TTL, "1")
        logger.debug(f"Marked packet {packet_id} as ingested (TTL: {Config.DEDUPE_TTL}s)")

    async def check_dedupe_outbox(self, packet_id: str) -> bool:
        """
        Check if reply has already been sent to outbox.

        Returns:
            True if already sent, False otherwise
        """
        key = Config.get_dedupe_outbox_key(packet_id)
        exists = await self._redis.exists(key)
        return bool(exists)

    async def mark_dedupe_outbox(self, packet_id: str):
        """Mark reply as sent to outbox with TTL."""
        key = Config.get_dedupe_outbox_key(packet_id)
        await self._redis.setex(key, Config.DEDUPE_TTL, "1")
        logger.debug(f"Marked packet {packet_id} as sent to outbox (TTL: {Config.DEDUPE_TTL}s)")

    async def enqueue_incoming(self, packet_dict: dict):
        """
        Enqueue ThoughtPacket to incoming queue.

        Args:
            packet_dict: ThoughtPacket as dictionary
        """
        packet_json = json.dumps(packet_dict)
        await self._redis.lpush(Config.QUEUE_INCOMING, packet_json)
        logger.info(f"Enqueued packet {packet_dict['packet_id']} to incoming queue")

    async def dequeue_incoming_to_inflight(self) -> Optional[dict]:
        """
        Atomically move packet from incoming to inflight (RPOPLPUSH).

        Returns:
            Packet dictionary or None if queue empty
        """
        packet_json = await self._redis.rpoplpush(
            Config.QUEUE_INCOMING,
            Config.QUEUE_INFLIGHT
        )
        if packet_json:
            packet = json.loads(packet_json)
            logger.debug(f"Moved packet {packet['packet_id']} to inflight")
            return packet
        return None

    async def remove_from_inflight(self, packet_dict: dict):
        """
        Remove packet from inflight queue.

        Args:
            packet_dict: Packet to remove
        """
        packet_json = json.dumps(packet_dict)
        removed = await self._redis.lrem(Config.QUEUE_INFLIGHT, 1, packet_json)
        if removed:
            logger.debug(f"Removed packet {packet_dict['packet_id']} from inflight")

    async def move_to_deadletter(self, packet_dict: dict):
        """
        Move packet to deadletter queue.

        Args:
            packet_dict: Packet to move
        """
        packet_json = json.dumps(packet_dict)
        await self._redis.lpush(Config.QUEUE_DEADLETTER, packet_json)
        logger.warning(f"Moved packet {packet_dict['packet_id']} to deadletter")

    async def enqueue_outbox(self, outbox_event: dict, agent_id: str):
        """
        Enqueue reply to per-agent Discord outbox.

        Args:
            outbox_event: Outbox event with packet_id, reply_text, etc.
            agent_id: Agent identifier (drevan, cypher, gaia)
        """
        outbox_key = Config.get_outbox_key(agent_id)
        event_json = json.dumps(outbox_event)
        await self._redis.lpush(outbox_key, event_json)
        logger.info(
            f"Enqueued to {agent_id} outbox: {outbox_event['packet_id']}"
        )

    async def get_queue_lengths(self) -> dict:
        """
        Get lengths of all queues including per-agent outboxes.

        Returns:
            Dictionary with queue lengths
        """
        incoming = await self._redis.llen(Config.QUEUE_INCOMING)
        inflight = await self._redis.llen(Config.QUEUE_INFLIGHT)
        deadletter = await self._redis.llen(Config.QUEUE_DEADLETTER)

        # Per-agent outboxes
        outbox_drevan = await self._redis.llen(Config.OUTBOX_DREVAN)
        outbox_cypher = await self._redis.llen(Config.OUTBOX_CYPHER)
        outbox_gaia = await self._redis.llen(Config.OUTBOX_GAIA)

        return {
            "incoming": incoming,
            "inflight": inflight,
            "deadletter": deadletter,
            "outbox": {
                "drevan": outbox_drevan,
                "cypher": outbox_cypher,
                "gaia": outbox_gaia
            }
        }

    async def update_brain_status(self, status: str):
        """
        Update Brain online/offline status.

        Args:
            status: "online" or "offline"
        """
        await self._redis.set(Config.BRAIN_STATUS_KEY, status)

        if status == "online":
            timestamp = datetime.now(timezone.utc).isoformat()
            await self._redis.set(Config.BRAIN_LAST_SEEN_KEY, timestamp)

    async def get_brain_status(self) -> str:
        """
        Get current Brain status.

        Returns:
            "online" or "offline" (defaults to "unknown" if not set)
        """
        status = await self._redis.get(Config.BRAIN_STATUS_KEY)
        return status or "unknown"
