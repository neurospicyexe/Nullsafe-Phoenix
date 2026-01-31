#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background drainer loop for processing queued packets.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

from shared.contracts import ThoughtPacket, AgentReply
from services.relay.brain_client import BrainClient
from services.relay.redis_client import RedisClient
from services.relay.config import Config

logger = logging.getLogger(__name__)


class QueueDrainer:
    """Background task to drain incoming queue and forward to Brain."""

    def __init__(self, redis_client: RedisClient, brain_client: BrainClient):
        """
        Initialize drainer.

        Args:
            redis_client: Redis client for queue operations
            brain_client: Brain HTTP client
        """
        self.redis = redis_client
        self.brain = brain_client
        self._running = False
        self._task = None

        # Track retry attempts per packet
        self._retry_counts: Dict[str, int] = {}

    async def start(self):
        """Start the drainer background task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._drain_loop())
            logger.info("Drainer started")

    async def stop(self):
        """Stop the drainer background task."""
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("Drainer stopped")

    async def _drain_loop(self):
        """Main drainer loop."""
        logger.info("Drainer loop starting")

        while self._running:
            try:
                # Check if Brain is reachable
                brain_healthy = await self.brain.health_check()

                if brain_healthy:
                    await self.redis.update_brain_status("online")
                    # Process one packet
                    await self._process_one_packet()
                else:
                    await self.redis.update_brain_status("offline")
                    logger.debug("Brain offline, skipping drain cycle")

                # Wait before next cycle
                await asyncio.sleep(Config.DRAINER_INTERVAL)

            except asyncio.CancelledError:
                logger.info("Drainer loop cancelled")
                break

            except Exception as e:
                logger.error(f"Error in drainer loop: {e}", exc_info=True)
                await asyncio.sleep(Config.DRAINER_INTERVAL)

    async def _process_one_packet(self):
        """
        Process one packet from incoming queue.

        Flow:
        1. RPOPLPUSH incoming -> inflight (atomic, crash-safe)
        2. Send to Brain
        3. On success: Emit to outbox, remove from inflight
        4. On failure: Increment retry count, requeue or deadletter
        """
        # Atomically move packet to inflight
        packet_dict = await self.redis.dequeue_incoming_to_inflight()

        if not packet_dict:
            # Queue empty
            return

        packet_id = packet_dict["packet_id"]

        try:
            # Reconstruct ThoughtPacket
            packet = ThoughtPacket(**packet_dict)

            # Get retry count
            retry_count = self._retry_counts.get(packet_id, 0)

            logger.info(
                f"Processing packet {packet_id} from queue "
                f"(attempt {retry_count + 1}/{Config.MAX_RETRIES})"
            )

            # Send to Brain
            reply = await self.brain.send_packet(
                packet,
                timeout=Config.BRAIN_TIMEOUT_DRAINER
            )

            if reply and reply.status == "ok":
                # Success! Emit to outbox
                await self._emit_to_outbox(packet, reply)

                # Remove from inflight
                await self.redis.remove_from_inflight(packet_dict)

                # Clear retry count
                if packet_id in self._retry_counts:
                    del self._retry_counts[packet_id]

                logger.info(f"Packet {packet_id} processed successfully")

            else:
                # Brain failed or returned error
                await self._handle_failure(packet_dict, retry_count)

        except Exception as e:
            logger.error(
                f"Error processing packet {packet_id}: {e}",
                exc_info=True
            )
            # Get retry count
            retry_count = self._retry_counts.get(packet_id, 0)
            await self._handle_failure(packet_dict, retry_count)

    async def _emit_to_outbox(self, packet: ThoughtPacket, reply: AgentReply):
        """
        Emit reply to Discord outbox with dedupe check.

        Args:
            packet: Original ThoughtPacket
            reply: AgentReply from Brain
        """
        packet_id = packet.packet_id

        # Check dedupe
        already_sent = await self.redis.check_dedupe_outbox(packet_id)

        if already_sent:
            logger.info(
                f"Reply for packet {packet_id} already in outbox (dedupe), skipping"
            )
            return

        # Mark as sent
        await self.redis.mark_dedupe_outbox(packet_id)

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
        await self.redis.enqueue_outbox(outbox_event, reply.agent_id)

        logger.info(
            f"Emitted reply for packet {packet_id} to outbox "
            f"(channel: {channel_id})"
        )

    async def _handle_failure(self, packet_dict: dict, retry_count: int):
        """
        Handle packet processing failure.

        Args:
            packet_dict: Packet that failed
            retry_count: Current retry count
        """
        packet_id = packet_dict["packet_id"]
        new_retry_count = retry_count + 1

        if new_retry_count >= Config.MAX_RETRIES:
            # Max retries exceeded, move to deadletter
            logger.error(
                f"Packet {packet_id} failed after {Config.MAX_RETRIES} attempts, "
                f"moving to deadletter"
            )

            await self.redis.move_to_deadletter(packet_dict)
            await self.redis.remove_from_inflight(packet_dict)

            # Clear retry count
            if packet_id in self._retry_counts:
                del self._retry_counts[packet_id]

        else:
            # Retry: move back to incoming queue
            logger.warning(
                f"Packet {packet_id} failed, requeueing "
                f"(attempt {new_retry_count}/{Config.MAX_RETRIES})"
            )

            # Update retry count
            self._retry_counts[packet_id] = new_retry_count

            # Move back to incoming queue
            await self.redis.enqueue_incoming(packet_dict)
            await self.redis.remove_from_inflight(packet_dict)

            # Exponential backoff
            backoff = min(2 ** new_retry_count, 60)
            logger.debug(f"Waiting {backoff}s before next retry for {packet_id}")
            await asyncio.sleep(backoff)
