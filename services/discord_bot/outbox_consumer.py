#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background outbox consumer for Discord bot.

Consumes replies from Redis outbox and sends to Discord channels.
"""

import asyncio
import logging
from typing import Dict, TYPE_CHECKING

from services.discord_bot.redis_client import DiscordRedisClient
from services.discord_bot.config import Config

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


class OutboxConsumer:
    """Background task to consume outbox and send to Discord."""

    def __init__(
        self,
        discord_client: "discord.Client",
        redis_client: DiscordRedisClient
    ):
        """
        Initialize outbox consumer.

        Args:
            discord_client: Discord client instance
            redis_client: Redis client for queue operations
        """
        self.discord = discord_client
        self.redis = redis_client
        self._running = False
        self._task = None

        # Track retry counts per packet
        self._retry_counts: Dict[str, int] = {}

    async def start(self):
        """Start the outbox consumer background task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._consume_loop())
            logger.info("Outbox consumer started")

    async def stop(self):
        """Stop the outbox consumer background task."""
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("Outbox consumer stopped")

    async def _consume_loop(self):
        """Main consumer loop."""
        logger.info("Outbox consumer loop starting")

        while self._running:
            try:
                # Process one outbox event
                await self._process_one_event()

                # Wait before next cycle
                await asyncio.sleep(Config.OUTBOX_POLL_INTERVAL)

            except asyncio.CancelledError:
                logger.info("Outbox consumer loop cancelled")
                break

            except Exception as e:
                logger.error(
                    f"Error in outbox consumer loop: {e}",
                    exc_info=True
                )
                await asyncio.sleep(Config.OUTBOX_POLL_INTERVAL)

    async def _process_one_event(self):
        """
        Process one outbox event.

        Flow:
        1. RPOPLPUSH outbox -> inflight (atomic, crash-safe)
        2. Check dedupe: if already sent, drop
        3. Send to Discord channel
        4. On success: Mark as sent, remove from inflight
        5. On failure: Increment retry count, requeue or deadletter
        """
        # Atomically move event to inflight
        event = await self.redis.dequeue_outbox_to_inflight()

        if not event:
            # Queue empty
            return

        packet_id = event["packet_id"]
        channel_id = event["channel_id"]
        reply_text = event["reply_text"]

        try:
            # Check dedupe
            already_sent = await self.redis.check_already_sent(packet_id)

            if already_sent:
                logger.info(
                    f"Packet {packet_id} already sent to Discord (dedupe), "
                    f"dropping inflight event"
                )
                await self.redis.remove_from_inflight(event)
                return

            # Get retry count
            retry_count = self._retry_counts.get(packet_id, 0)

            logger.info(
                f"Sending reply for packet {packet_id} to channel {channel_id} "
                f"(attempt {retry_count + 1}/{Config.MAX_SEND_RETRIES})"
            )

            # Send to Discord
            success = await self._send_to_discord(channel_id, reply_text, packet_id)

            if success:
                # Success! Mark as sent and remove from inflight
                await self.redis.mark_as_sent(packet_id)
                await self.redis.remove_from_inflight(event)

                # Clear retry count
                if packet_id in self._retry_counts:
                    del self._retry_counts[packet_id]

                logger.info(
                    f"Successfully sent reply for packet {packet_id} "
                    f"to channel {channel_id}"
                )

            else:
                # Discord send failed
                await self._handle_send_failure(event, retry_count)

        except Exception as e:
            logger.error(
                f"Error processing outbox event for packet {packet_id}: {e}",
                exc_info=True
            )
            retry_count = self._retry_counts.get(packet_id, 0)
            await self._handle_send_failure(event, retry_count)

    async def _send_to_discord(
        self,
        channel_id: str,
        reply_text: str,
        packet_id: str
    ) -> bool:
        """
        Send message to Discord channel.

        Args:
            channel_id: Discord channel ID
            reply_text: Message text to send
            packet_id: Packet ID for logging

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get channel
            channel = self.discord.get_channel(int(channel_id))

            if not channel:
                logger.error(
                    f"Channel {channel_id} not found for packet {packet_id}"
                )
                return False

            # Send message
            await channel.send(reply_text)

            logger.debug(
                f"Sent message to channel {channel_id} for packet {packet_id}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to send to Discord channel {channel_id} "
                f"for packet {packet_id}: {e}",
                exc_info=True
            )
            return False

    async def _handle_send_failure(self, event: dict, retry_count: int):
        """
        Handle Discord send failure.

        Args:
            event: Outbox event that failed
            retry_count: Current retry count
        """
        packet_id = event["packet_id"]
        new_retry_count = retry_count + 1

        if new_retry_count >= Config.MAX_SEND_RETRIES:
            # Max retries exceeded, move to deadletter
            logger.error(
                f"Outbox event for packet {packet_id} failed after "
                f"{Config.MAX_SEND_RETRIES} attempts, moving to deadletter"
            )

            await self.redis.move_to_deadletter(event)
            await self.redis.remove_from_inflight(event)

            # Clear retry count
            if packet_id in self._retry_counts:
                del self._retry_counts[packet_id]

        else:
            # Retry: move back to outbox queue
            logger.warning(
                f"Outbox event for packet {packet_id} failed, requeueing "
                f"(attempt {new_retry_count}/{Config.MAX_SEND_RETRIES})"
            )

            # Update retry count
            self._retry_counts[packet_id] = new_retry_count

            # Move back to outbox (re-enqueue)
            # Note: We need to reconstruct the event in queue
            # For simplicity, we'll just remove from inflight and add back to outbox
            await self.redis.remove_from_inflight(event)

            # Re-add to outbox (front of queue for immediate retry)
            import json
            event_json = json.dumps(event)
            # Use lpush to add to front
            await self.redis._redis.lpush(Config.OUTBOX_QUEUE, event_json)

            # Exponential backoff
            backoff = min(2 ** new_retry_count, 60)
            logger.debug(
                f"Waiting {backoff}s before next retry for packet {packet_id}"
            )
            await asyncio.sleep(backoff)
