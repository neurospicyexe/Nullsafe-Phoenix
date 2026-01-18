#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - Discord Bot

ONLY component that talks to Discord API.
Handles message ingress and outbox consumption.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import discord
from discord.ext import commands

from shared.contracts import ThoughtPacket
from services.discord_bot.config import Config
from services.discord_bot.redis_client import DiscordRedisClient
from services.discord_bot.relay_client import RelayClient
from services.discord_bot.outbox_consumer import OutboxConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class PhoenixBot(commands.Bot):
    """Discord bot for Nullsafe Phoenix."""

    def __init__(self):
        """Initialize bot with intents."""
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content

        super().__init__(
            command_prefix="!",  # Not used for message handling, but required
            intents=intents
        )

        # Initialize clients
        self.redis_client = DiscordRedisClient()
        self.relay_client = RelayClient()
        self.outbox_consumer = None

    async def setup_hook(self):
        """
        Setup hook called when bot starts.

        Connects Redis and Relay clients, starts outbox consumer.
        """
        logger.info("Setting up Phoenix bot...")

        try:
            # Connect clients
            await self.redis_client.connect()
            await self.relay_client.connect()

            # Start outbox consumer
            self.outbox_consumer = OutboxConsumer(self, self.redis_client)
            await self.outbox_consumer.start()

            logger.info("Phoenix bot setup complete")

        except Exception as e:
            logger.error(f"Failed to setup bot: {e}", exc_info=True)
            raise

    async def on_ready(self):
        """Called when bot is ready."""
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")

    async def on_message(self, message: discord.Message):
        """
        Handle incoming Discord messages.

        Ingress flow:
        1. Ignore bots and self
        2. Determine agent_id from channel mapping
        3. Construct ThoughtPacket
        4. POST to Relay /ingest
        5. Handle response (ok or queued)

        Args:
            message: Discord message object
        """
        # Ignore bots and self
        if message.author.bot:
            return

        if message.author == self.user:
            return

        logger.info(
            f"Received message from {message.author} in channel {message.channel.id}: "
            f"{message.content[:50]}..."
        )

        try:
            # Determine agent_id from channel mapping
            channel_id_str = str(message.channel.id)
            agent_id = Config.CHANNEL_AGENT_MAPPING.get(
                channel_id_str,
                Config.DEFAULT_AGENT
            )

            # Generate packet ID
            packet_id = str(uuid.uuid4())

            # Construct metadata
            metadata = {
                "channel_id": channel_id_str,
                "platform": "discord",
                "author_id": str(message.author.id),
                "author_name": str(message.author),
            }

            # Add guild_id if present (not present in DMs)
            if message.guild:
                metadata["guild_id"] = str(message.guild.id)
                metadata["guild_name"] = message.guild.name

            # Construct ThoughtPacket
            packet = ThoughtPacket(
                packet_id=packet_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="discord",
                user_id=f"discord:{message.author.id}",
                thread_id=channel_id_str,  # For Discord, thread_id = channel_id
                agent_id=agent_id,
                message=message.content,
                metadata=metadata
            )

            logger.info(
                f"Constructed ThoughtPacket {packet_id} for agent {agent_id}"
            )

            # POST to Relay /ingest
            reply = await self.relay_client.ingest_packet(packet)

            if not reply:
                # Relay unreachable
                await message.channel.send(
                    "⚠️ System temporarily unavailable. Please try again later."
                )
                return

            # Handle response
            if reply.status == "ok":
                # Fast path success - send reply
                logger.info(
                    f"Fast path success for packet {packet_id}, "
                    f"sending reply"
                )
                await message.channel.send(reply.reply_text)

            elif reply.status == "queued":
                # Queued for processing
                short_id = packet_id[:8]
                logger.info(
                    f"Packet {packet_id} queued, "
                    f"sending acknowledgment"
                )
                await message.channel.send(
                    f"⏳ Queued (ID: {short_id})"
                )

            else:
                # Error or other status
                logger.warning(
                    f"Unexpected status {reply.status} for packet {packet_id}"
                )
                await message.channel.send(
                    f"⚠️ Error processing message (status: {reply.status})"
                )

        except Exception as e:
            logger.error(
                f"Error handling message from {message.author}: {e}",
                exc_info=True
            )
            await message.channel.send(
                "⚠️ An error occurred processing your message."
            )

    async def close(self):
        """Cleanup when bot shuts down."""
        logger.info("Shutting down Phoenix bot...")

        try:
            # Stop outbox consumer
            if self.outbox_consumer:
                await self.outbox_consumer.stop()

            # Close clients
            await self.relay_client.close()
            await self.redis_client.close()

            logger.info("Phoenix bot shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

        await super().close()


async def main():
    """Main entry point."""
    # Check for Discord token
    if not Config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        return

    # Create and run bot
    bot = PhoenixBot()

    try:
        await bot.start(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
