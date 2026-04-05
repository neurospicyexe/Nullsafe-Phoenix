#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration for Relay service.
"""

import os
from typing import Optional


class Config:
    """Relay service configuration."""

    # Brain service
    BRAIN_SERVICE_URL: str = os.getenv(
        "BRAIN_SERVICE_URL", "http://127.0.0.1:8001"
    )
    BRAIN_TIMEOUT_FAST: int = int(os.getenv("BRAIN_TIMEOUT_FAST", "5"))
    BRAIN_TIMEOUT_DRAINER: int = int(os.getenv("BRAIN_TIMEOUT_DRAINER", "30"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

    # Queue settings
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "5"))
    DRAINER_INTERVAL: int = int(os.getenv("DRAINER_INTERVAL", "2"))
    DEDUPE_TTL: int = int(os.getenv("DEDUPE_TTL", "86400"))

    # Redis key prefixes
    QUEUE_INCOMING = "phx:queue:incoming"
    QUEUE_INFLIGHT = "phx:queue:inflight"
    QUEUE_DEADLETTER = "phx:queue:deadletter"

    # Per-agent outbox queues
    OUTBOX_DREVAN = "phx:outbox:discord:drevan"
    OUTBOX_CYPHER = "phx:outbox:discord:cypher"
    OUTBOX_GAIA = "phx:outbox:discord:gaia"

    # Legacy single outbox (deprecated, kept for backward compat)
    OUTBOX_DISCORD = "phx:outbox:discord"

    DEDUPE_INGEST_PREFIX = "phx:dedupe:ingest"
    DEDUPE_OUTBOX_PREFIX = "phx:dedupe:outbox"
    BRAIN_STATUS_KEY = "phx:relay:brain_status"
    BRAIN_LAST_SEEN_KEY = "phx:relay:last_seen"

    @staticmethod
    def get_dedupe_ingest_key(packet_id: str) -> str:
        """Get dedupe key for ingest."""
        return f"{Config.DEDUPE_INGEST_PREFIX}:{packet_id}"

    @staticmethod
    def get_dedupe_outbox_key(packet_id: str) -> str:
        """Get dedupe key for outbox."""
        return f"{Config.DEDUPE_OUTBOX_PREFIX}:{packet_id}"

    @staticmethod
    def get_outbox_key(agent_id: str) -> str:
        """Get outbox key for specific agent."""
        return f"phx:outbox:discord:{agent_id}"
