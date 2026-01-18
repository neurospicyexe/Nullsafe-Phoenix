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
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Outbox consumer settings
    OUTBOX_POLL_INTERVAL: int = 1  # Seconds
    MAX_SEND_RETRIES: int = 5
    DEDUPE_TTL: int = 86400  # 24 hours

    # Redis keys
    OUTBOX_QUEUE = "phx:outbox:discord"
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
