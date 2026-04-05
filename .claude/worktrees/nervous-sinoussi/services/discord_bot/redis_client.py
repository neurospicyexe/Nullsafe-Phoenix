#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis client for Discord bot outbox consumer.
"""

import json
import logging
from typing import Optional

import redis.asyncio as redis

from services.discord_bot.config import Config

logger = logging.getLogger(__name__)


class DiscordRedisClient:
    """Redis client for Discord bot outbox operations."""

    def __init__(self):
        """Initialize Redis client."""
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = await redis.from_url(
                Config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Discord bot connected to Redis at {Config.REDIS_URL}")

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Discord bot Redis connection closed")

    async def dequeue_outbox_to_inflight(self) -> Optional[dict]:
        """
        Atomically move outbox event from queue to inflight (RPOPLPUSH).

        Returns:
            Outbox event dictionary or None if queue empty
        """
        event_json = await self._redis.rpoplpush(
            Config.OUTBOX_QUEUE,
            Config.OUTBOX_INFLIGHT
        )

        if event_json:
            event = json.loads(event_json)
            logger.debug(
                f"Moved outbox event for packet {event['packet_id']} to inflight"
            )
            return event

        return None

    async def remove_from_inflight(self, event: dict):
        """
        Remove outbox event from inflight queue.

        Args:
            event: Outbox event to remove
        """
        event_json = json.dumps(event)
        removed = await self._redis.lrem(Config.OUTBOX_INFLIGHT, 1, event_json)

        if removed:
            logger.debug(
                f"Removed outbox event for packet {event['packet_id']} from inflight"
            )

    async def move_to_deadletter(self, event: dict):
        """
        Move outbox event to deadletter queue.

        Args:
            event: Outbox event to move
        """
        event_json = json.dumps(event)
        await self._redis.lpush(Config.OUTBOX_DEADLETTER, event_json)

        logger.warning(
            f"Moved outbox event for packet {event['packet_id']} to deadletter"
        )

    async def check_already_sent(self, packet_id: str) -> bool:
        """
        Check if packet has already been sent to Discord.

        Args:
            packet_id: Packet ID to check

        Returns:
            True if already sent, False otherwise
        """
        exists = await self._redis.sismember(Config.DISCORD_SENT_SET, packet_id)
        return bool(exists)

    async def mark_as_sent(self, packet_id: str):
        """
        Mark packet as sent to Discord with TTL.

        Args:
            packet_id: Packet ID to mark
        """
        # Add to set
        await self._redis.sadd(Config.DISCORD_SENT_SET, packet_id)

        # Set TTL on the set (Note: TTL applies to entire set, not individual members)
        # For per-member TTL, we'd use individual keys instead
        # Using simple approach for Day One
        await self._redis.expire(Config.DISCORD_SENT_SET, Config.DEDUPE_TTL)

        logger.debug(f"Marked packet {packet_id} as sent to Discord")

    async def requeue_outbox(self, event: dict):
        """
        Re-enqueue outbox event to front of queue for immediate retry.

        Args:
            event: Outbox event to re-enqueue
        """
        event_json = json.dumps(event)
        await self._redis.lpush(Config.OUTBOX_QUEUE, event_json)

        logger.debug(
            f"Re-enqueued outbox event for packet {event['packet_id']} to front of queue"
        )

    async def get_queue_lengths(self) -> dict:
        """
        Get lengths of outbox queues.

        Returns:
            Dictionary with queue lengths
        """
        outbox = await self._redis.llen(Config.OUTBOX_QUEUE)
        inflight = await self._redis.llen(Config.OUTBOX_INFLIGHT)
        deadletter = await self._redis.llen(Config.OUTBOX_DEADLETTER)

        return {
            "outbox": outbox,
            "inflight": inflight,
            "deadletter": deadletter
        }
