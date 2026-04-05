#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration for Discord bot.
"""

import os


class Config:
    """Discord bot configuration."""

    # Discord
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")

    # Relay API
    RELAY_API_URL: str = os.getenv(
        "RELAY_API_URL", "http://localhost:8000"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

    # Agent-specific configuration
    AGENT_ID: str = os.getenv("AGENT_ID", "cypher")
    OUTBOX_KEY: str = os.getenv("OUTBOX_KEY", "phx:outbox:discord")

    # Outbox consumer settings
    OUTBOX_POLL_INTERVAL: int = 1  # Seconds
    MAX_SEND_RETRIES: int = 5
    DEDUPE_TTL: int = 86400  # 24 hours

    # Redis keys - use OUTBOX_KEY from env
    OUTBOX_QUEUE = OUTBOX_KEY
    OUTBOX_INFLIGHT = "phx:outbox:inflight"
    OUTBOX_DEADLETTER = "phx:outbox:deadletter"
    DISCORD_SENT_SET = "phx:discord:sent"

    # Day One: Hardcoded channel -> agent mapping
    # In production, this would be configurable or stored in a database
    CHANNEL_AGENT_MAPPING = {
        # Example: "1234567890": "cypher",
        # For testing, we'll use default agent per message if not in mapping
    }

    DEFAULT_AGENT = "cypher"  # Default if channel not in mapping

    @staticmethod
    def validate():
        """Validate required config."""
        if not Config.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required")

        if Config.AGENT_ID not in ["drevan", "cypher", "gaia"]:
            raise ValueError(f"Invalid AGENT_ID: {Config.AGENT_ID}")

    @staticmethod
    def print_safe_summary():
        """Print config summary (no secrets)."""
        print("=" * 60)
        print("DISCORD BOT CONFIGURATION:")
        print(f"  Agent ID: {Config.AGENT_ID}")
        print(f"  Outbox key: {Config.OUTBOX_KEY}")
        print(f"  Relay URL: {Config.RELAY_API_URL}")
        # Hide password in Redis URL if present
        redis_display = (
            Config.REDIS_URL.split("@")[-1]
            if "@" in Config.REDIS_URL
            else Config.REDIS_URL
        )
        print(f"  Redis URL: {redis_display}")
        print(f"  Token: {'✓ Set' if Config.DISCORD_TOKEN else '✗ Not set'}")
        print("=" * 60)
